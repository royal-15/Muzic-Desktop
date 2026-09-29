"""Download worker thread for processing individual download tasks."""
import os
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


class DownloadWorker(QThread):
    """Worker thread for downloading audio with the bundled yt-dlp module."""

    progress_updated = Signal(int, str, str)
    status_changed = Signal(str)
    finished = Signal(str, str, str)

    def __init__(self, task: DownloadTask, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.task = task
        self.settings = settings
        self._should_cancel = False
        self._started_at = 0.0
        self._timeout_seconds = 300
        self._output_file: Optional[str] = None

    def cancel(self) -> None:
        """Request cancellation; yt-dlp observes it in its progress hook."""
        self._should_cancel = True
        logger.info(f"Cancellation requested for download task {self.task.id}")

    def run(self) -> None:
        logger.info(f"Starting download task {self.task.id}: {self.task.url}")
        self.status_changed.emit("Preparing download...")

        try:
            os.makedirs(self.settings.output_dir, exist_ok=True)
            self._timeout_seconds = self._get_timeout()
            self._started_at = time.monotonic()
            query = self.task.url
            if not is_youtube_url(query) and not query.startswith("ytsearch"):
                query = f"ytsearch1:{query}"

            max_attempts = max(1, getattr(self.settings, "retry_attempts", 0) + 1)
            error_message = "Download failed"
            for attempt in range(1, max_attempts + 1):
                if self._should_cancel:
                    break
                self._started_at = time.monotonic()
                self._output_file = None
                if attempt > 1:
                    logger.info(
                        f"Retrying download task {self.task.id} "
                        f"(attempt {attempt}/{max_attempts})"
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
                    logger.exception(f"Exception in download task {self.task.id}")
                    error_message = self._classify_error_message(str(error))

                if self._should_cancel:
                    break
                if attempt == max_attempts or not self._is_retryable_error(error_message):
                    break

                backoff_seconds = min(5 * attempt, 30)
                logger.info(
                    f"Will retry task {self.task.id} in {backoff_seconds} seconds "
                    "due to transient error."
                )
                if self._wait_before_retry(backoff_seconds):
                    break

            if self._should_cancel:
                self.finished.emit(STATUS_CANCELLED, "", "Download cancelled by user")
            else:
                logger.error(f"Task {self.task.id} failed: {error_message}")
                self.finished.emit(STATUS_FAILED, "", error_message)
        except Exception as error:
            logger.exception(f"Exception in download task {self.task.id}")
            self.finished.emit(STATUS_FAILED, "", str(error))

    def _build_options(self) -> dict:
        options = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(self.settings.output_dir, "%(title)s.%(ext)s"),
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
        if self.settings.ffmpeg_path:
            options["ffmpeg_location"] = self.settings.ffmpeg_path

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
        if self._output_file:
            return
        if isinstance(result, dict):
            filepath = result.get("filepath") or result.get("_filename")
            if filepath:
                self._output_file = filepath
                return
            entries = result.get("entries") or []
            for entry in entries:
                if isinstance(entry, dict) and (entry.get("filepath") or entry.get("_filename")):
                    self._output_file = entry.get("filepath") or entry.get("_filename")
                    return

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
        text = (raw_error or "").strip()
        if not text:
            return "Download failed"
        lower = text.lower()
        if "download cancelled by user" in lower:
            return "Download cancelled by user"
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


class _YtDlpLogger:
    """Forward yt-dlp diagnostics to Muzic's application logger."""

    def debug(self, message: str) -> None:
        if message.startswith("[debug]"):
            logger.debug(message)

    def info(self, message: str) -> None:
        logger.info(message)

    def warning(self, message: str) -> None:
        logger.warning(message)

    def error(self, message: str) -> None:
        logger.error(message)
