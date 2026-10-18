"""Download worker thread for processing individual download tasks."""
import os
import random
import shutil
import time
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QThread, Signal
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from ..config.constants import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_DOWNLOADING,
    STATUS_FAILED,
)
from ..config.settings import AppSettings
from ..utils.logger import logger
from ..utils.validators import is_youtube_url
from .ytdlp_options import (
    authentication_options,
    javascript_runtime_options,
    redact_sensitive_text,
)
from .rate_limit import RateLimitCoordinator


@dataclass
class DownloadTask:
    """Represents a single download task."""

    id: int
    url: str
    status: str = STATUS_DOWNLOADING
    progress: int = 0
    speed: str = ""
    eta: str = ""
    output_file: Optional[str] = None
    error_message: Optional[str] = None
    output_dir: str = ""
    title: str = ""
    status_message: str = ""


class DownloadWorker(QThread):
    """Worker thread for downloading audio with the bundled yt-dlp module."""

    progress_updated = Signal(int, str, str)
    title_updated = Signal(str)
    status_changed = Signal(str)
    finished = Signal(str, str, str)

    def __init__(
        self,
        task: DownloadTask,
        settings: AppSettings,
        parent=None,
        rate_limit_coordinator: Optional[RateLimitCoordinator] = None,
    ):
        super().__init__(parent)
        self.task = task
        self.settings = settings
        self.rate_limit_coordinator = rate_limit_coordinator or RateLimitCoordinator()
        self._should_cancel = False
        self._started_at = 0.0
        self._timeout_seconds = 300
        self._output_file: Optional[str] = None
        self._last_title = task.title

    def cancel(self) -> None:
        """Request cancellation; yt-dlp observes it in its progress hook."""
        self._should_cancel = True
        logger.info(f"Cancellation requested for download task {self.task.id}")

    def run(self) -> None:
        logger.info(f"Starting download task {self.task.id}: {self.task.url}")
        self.status_changed.emit("Preparing download...")

        try:
            output_dir = self.task.output_dir or self.settings.output_dir
            os.makedirs(output_dir, exist_ok=True)
            self._timeout_seconds = self._get_timeout()
            self._started_at = time.monotonic()
            query = self.task.url
            if not is_youtube_url(query) and not query.startswith("ytsearch"):
                query = f"ytsearch1:{query}"

            try:
                max_general_retries = max(0, int(getattr(self.settings, "retry_attempts", 0)))
            except (TypeError, ValueError):
                max_general_retries = 0
            rate_limit_retries = 0
            general_retries = 0
            attempt = 0
            error_message = "Download failed"
            max_rate_limit_retries = 3
            while True:
                if self._should_cancel:
                    break
                if self.rate_limit_coordinator.remaining() > 0:
                    self.status_changed.emit("Waiting for YouTube rate limit cooldown...")
                if self.rate_limit_coordinator.wait(lambda: self._should_cancel):
                    break
                attempt += 1
                self.status_changed.emit(
                    "Retrying download..." if attempt > 1 else "Preparing download..."
                )
                self._started_at = time.monotonic()
                self._output_file = None
                if attempt > 1:
                    logger.info(
                        f"Retrying download task {self.task.id} "
                        f"(attempt {attempt})"
                    )

                try:
                    options = self._build_options()
                    with YoutubeDL(options) as ydl:
                        result = ydl.extract_info(query, download=True)
                    self._record_output(result)
                    self.progress_updated.emit(100, "", "")
                    self.finished.emit(
                        STATUS_COMPLETED, self._output_file or "", ""
                    )
                    logger.info(f"Task {self.task.id} completed successfully")
                    return
                except DownloadError as error:
                    error_message = self._classify_error_message(str(error))
                except Exception as error:
                    logger.error(
                        f"Exception in download task {self.task.id}: "
                        f"{redact_sensitive_text(str(error))}"
                    )
                    error_message = self._classify_error_message(str(error))

                if self._should_cancel:
                    break
                if self._is_rate_limit_error(error_message):
                    if rate_limit_retries >= max_rate_limit_retries:
                        break
                    rate_limit_retries += 1
                    backoff_seconds = min(60 * (2 ** (rate_limit_retries - 1)), 900)
                    backoff_seconds += random.uniform(0, min(15, backoff_seconds * 0.1))
                    shared_delay = self.rate_limit_coordinator.defer(backoff_seconds)
                    logger.warning(
                        f"Task {self.task.id} received HTTP 429; pausing YouTube "
                        f"requests for about {int(shared_delay)} seconds "
                        f"(rate-limit retry {rate_limit_retries}/{max_rate_limit_retries})."
                    )
                    self.status_changed.emit("Waiting for YouTube rate limit cooldown...")
                    continue
                elif general_retries < max_general_retries and self._is_retryable_error(error_message):
                    general_retries += 1
                    backoff_seconds = min(5 * general_retries, 30)
                else:
                    break
                logger.info(
                    f"Will retry task {self.task.id} in {backoff_seconds} seconds "
                    "due to transient error."
                )
                if self._wait_before_retry(backoff_seconds):
                    break

            if self._should_cancel:
                self.finished.emit(STATUS_CANCELLED, "", "Download cancelled by user")
            else:
                if rate_limit_retries:
                    error_message += (
                        f" Muzic applied a shared cooldown and retried "
                        f"{rate_limit_retries} time(s). Wait longer before trying again; "
                        "YouTube may be limiting this network's IP address."
                    )
                logger.error(f"Task {self.task.id} failed: {error_message}")
                self.finished.emit(STATUS_FAILED, "", error_message)
        except Exception as error:
            safe_error = redact_sensitive_text(str(error))
            logger.error(f"Exception in download task {self.task.id}: {safe_error}")
            self.finished.emit(STATUS_FAILED, "", safe_error)

    def _build_options(self) -> dict:
        options = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(self.task.output_dir or self.settings.output_dir, "%(title)s.%(ext)s"),
            "noplaylist": False,
            "quiet": True,
            "no_warnings": True,
            "logger": _YtDlpLogger(),
            "progress_hooks": [self._progress_hook],
            "postprocessor_hooks": [self._postprocessor_hook],
            "socket_timeout": self._timeout_seconds,
            "retries": 0,
            "fragment_retries": 0,
            "ignoreerrors": False,
        }
        options.update(javascript_runtime_options(self.settings))
        options.update(authentication_options(self.settings))
        ffmpeg_path = (self.settings.ffmpeg_path or "").strip()
        if ffmpeg_path:
            resolved_ffmpeg = ffmpeg_path if os.path.isfile(ffmpeg_path) or os.path.isdir(ffmpeg_path) else shutil.which(ffmpeg_path)
            if not resolved_ffmpeg and os.path.basename(ffmpeg_path).lower() in {"ffmpeg.exe", "ffmpeg"}:
                resolved_ffmpeg = shutil.which("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
            options["ffmpeg_location"] = resolved_ffmpeg or ffmpeg_path

        if self.settings.default_format:
            options["format"] = "bestaudio/best"
            options["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": self.settings.default_format,
                "preferredquality": self._audio_quality(),
            }]
        if self.settings.embed_metadata:
            options.setdefault("postprocessors", []).append({"key": "FFmpegMetadata"})
        if self.settings.embed_thumbnail:
            options["writethumbnail"] = True
            options.setdefault("postprocessors", []).append({
                "key": "EmbedThumbnail",
                "already_have_thumbnail": False,
            })
        return options

    def _audio_quality(self) -> str:
        quality = self.settings.default_quality
        if quality == "Best":
            return "0"
        return quality.replace("kbps", "k")

    def _progress_hook(self, data: dict) -> None:
        if self._should_cancel:
            raise DownloadError("Download cancelled by user")
        if time.monotonic() - self._started_at > self._timeout_seconds:
            raise DownloadError(
                f"Download timed out after {self._timeout_seconds} seconds"
            )

        info = data.get("info_dict", {})
        self._emit_title(info.get("title"))
        filepath = info.get("filepath") or info.get("_filename")
        if filepath:
            self._output_file = filepath

        if data.get("status") == "finished":
            self.status_changed.emit("Converting audio...")
            return

        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        downloaded = data.get("downloaded_bytes", 0)
        if total:
            progress = max(0, min(99, int(downloaded * 100 / total)))
            self.progress_updated.emit(
                progress,
                self._format_speed(data.get("speed")),
                self._format_eta(data.get("eta")),
            )

    def _postprocessor_hook(self, data: dict) -> None:
        info = data.get("info_dict", {})
        filepath = info.get("filepath") or info.get("_filename")
        if filepath:
            self._output_file = filepath

    def _record_output(self, result: Optional[dict]) -> None:
        if isinstance(result, dict):
            self._emit_title(result.get("title"))
            for entry in result.get("entries") or []:
                if isinstance(entry, dict):
                    self._emit_title(entry.get("title"))
                    if entry.get("filepath") or entry.get("_filename"):
                        self._output_file = entry.get("filepath") or entry.get("_filename")
                        return

        if self._output_file:
            return
        if isinstance(result, dict):
            filepath = result.get("filepath") or result.get("_filename")
            if filepath:
                self._output_file = filepath
                return

    def _emit_title(self, title: Optional[str]) -> None:
        if title:
            title = str(title)
            if title != self._last_title:
                self._last_title = title
                self.title_updated.emit(title)

    def _get_timeout(self) -> int:
        try:
            value = int(getattr(self.settings, "timeout_seconds", 300) or 300)
        except (TypeError, ValueError):
            value = 300
        return max(30, min(value, 3600))

    def _wait_before_retry(self, seconds: int) -> bool:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self._should_cancel:
                return True
            time.sleep(min(0.2, deadline - time.monotonic()))
        return self._should_cancel

    @staticmethod
    def _format_speed(speed: Optional[float]) -> str:
        if not speed or speed < 0:
            return ""
        value = float(speed)
        for unit in ("B/s", "KiB/s", "MiB/s", "GiB/s"):
            if value < 1024 or unit == "GiB/s":
                return f"{value:.2f}{unit}"
            value /= 1024
        return ""

    @staticmethod
    def _format_eta(eta: Optional[int]) -> str:
        if eta is None:
            return ""
        eta = max(0, int(eta))
        hours, remainder = divmod(eta, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _classify_error_message(raw_error: str) -> str:
        text = redact_sensitive_text((raw_error or "").strip())
        if not text:
            return "Download failed"
        lower = text.lower()
        if "download cancelled by user" in lower:
            return "Download cancelled by user"
        if any(term in lower for term in (
            "sign in to confirm", "confirm you’re not a bot", "confirm you're not a bot",
            "not a bot", "cookies are no longer valid", "authentication required",
        )):
            return (
                "YouTube asked for sign-in or bot verification. Sign in to YouTube in your "
                "default browser, then enable Settings → YouTube Authentication → Default "
                "browser session and retry. Cookies may help, but some YouTube challenges "
                "cannot be cleared this way."
            )
        if DownloadWorker._is_rate_limit_error(lower):
            return (
                "YouTube is rate limiting requests (HTTP 429). Wait before trying again and reduce parallel downloads. "
                "Signing in may not clear an IP-based rate limit."
            )
        if "cookie" in lower and any(term in lower for term in (
            "could not copy", "failed to decrypt", "permission denied", "database is locked",
        )):
            return (
                "Muzic could not read the detected browser's YouTube session. Confirm that you "
                "are signed in, close the browser and retry, or choose a cookies file in Settings."
            )
        if any(term in lower for term in (
            "failed to load cookies", "cookie file", "cookies file",
        )):
            return (
                "Muzic could not load the configured YouTube cookies. Check that the cookies "
                "file exists and is in Netscape format, or select a signed-in browser session in Settings."
            )
        if any(term in lower for term in (
            "no supported javascript runtime", "javascript runtime", "js challenge",
            "javascript challenge", "nsig extraction failed", "signature extraction failed",
            "challenge solving failed",
        )):
            return (
                "YouTube's JavaScript challenge could not be solved. Enable Deno in Settings "
                "for fuller extraction support, then retry."
            )
        if "timed out after" in lower:
            return text
        if any(term in lower for term in ("connection error", "connection aborted", "timed out", "connection reset")):
            return "Network error while contacting YouTube. Please check your connection and try again."
        if "ffmpeg" in lower and any(term in lower for term in ("not found", "no such file", "not installed")):
            return "FFmpeg was not found. Check the FFmpeg path in Settings."
        if len(text) > 500:
            return text[:500] + "..."
        return text

    @staticmethod
    def _is_retryable_error(message: Optional[str]) -> bool:
        if not message:
            return False
        lower = message.lower()
        return any(term in lower for term in (
            "network error", "timed out", "temporarily unavailable",
            "connection aborted", "connection reset",
        ))

    @staticmethod
    def _is_rate_limit_error(message: Optional[str]) -> bool:
        lower = (message or "").lower()
        return "429" in lower or "too many requests" in lower


class _YtDlpLogger:
    """Forward yt-dlp diagnostics to Muzic's application logger."""

    def debug(self, message: str) -> None:
        if message.startswith("[debug]"):
            logger.debug(redact_sensitive_text(message))

    def info(self, message: str) -> None:
        logger.info(redact_sensitive_text(message))

    def warning(self, message: str) -> None:
        logger.warning(redact_sensitive_text(message))

    def error(self, message: str) -> None:
        logger.error(redact_sensitive_text(message))
