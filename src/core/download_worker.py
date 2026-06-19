"""Download worker thread for processing individual download tasks."""
import os
import re
import subprocess
import time
from typing import Optional
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from ..config.settings import AppSettings
from ..config.constants import STATUS_DOWNLOADING, STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED
from ..utils.logger import logger
from ..utils.validators import is_spotify_url


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
    """Worker thread for downloading music from Spotify or YouTube."""
    
    # Signals
    progress_updated = Signal(int, str, str)  # progress, speed, eta
    status_changed = Signal(str)  # status message
    finished = Signal(str, str, str)  # status, output_file, error_message
    
    def __init__(self, task: DownloadTask, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.task = task
        self.settings = settings
        self._should_cancel = False
        self._process: Optional[subprocess.Popen] = None
    
    def cancel(self) -> None:
        """Cancel the download."""
        self._should_cancel = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                logger.info(f"Cancelled download task {self.task.id}")
            except Exception as e:
                logger.error(f"Error cancelling task {self.task.id}: {e}")
    
    def run(self) -> None:
        """Execute the download task."""
        logger.info(f"Starting download task {self.task.id}: {self.task.url}")
        self.status_changed.emit("Preparing download...")
        
        try:
            # Ensure output directory exists
            os.makedirs(self.settings.output_dir, exist_ok=True)
            
            # Build command based on URL type or search query
            if is_spotify_url(self.task.url):
                cmd = self._build_spotify_command()
            elif self._is_youtube_search(self.task.url):
                cmd = self._build_youtube_command()
            elif self.task.url.startswith("ytsearch"):
                # yt-dlp search query
                cmd = self._build_youtube_command()
            else:
                # Assume it's a Spotify search query (song name)
                cmd = self._build_spotify_command()
            
            logger.debug(f"Command: {' '.join(cmd)}")
            
            # Execute download with retries and timeout awareness
            max_attempts = max(1, getattr(self.settings, "retry_attempts", 0) + 1)
            attempt = 1
            success = False
            output_file: Optional[str] = None
            error_msg: Optional[str] = None
            
            while attempt <= max_attempts and not self._should_cancel:
                if attempt > 1:
                    logger.info(
                        f"Retrying download task {self.task.id} "
                        f"(attempt {attempt}/{max_attempts})"
                    )
                
                success, output_file, error_msg = self._execute_command(cmd)
                
                if success or self._should_cancel:
                    break
                
                # Classify and potentially shorten the error message for UI/logs
                classified_error = self._classify_error_message(error_msg or "")
                error_msg = classified_error
                
                # Only retry on transient / retryable errors
                if not self._is_retryable_error(error_msg) or attempt == max_attempts:
                    break
                
                # Simple exponential backoff between retries (max ~30s)
                backoff_seconds = min(5 * attempt, 30)
                logger.info(
                    f"Will retry task {self.task.id} in {backoff_seconds} seconds "
                    "due to transient error."
                )
                time.sleep(backoff_seconds)
                attempt += 1
            
            if self._should_cancel:
                self.finished.emit(STATUS_CANCELLED, "", "Download cancelled by user")
                return
            
            if success:
                logger.info(f"Task {self.task.id} completed successfully")
                self.finished.emit(STATUS_COMPLETED, output_file or "", "")
            else:
                logger.error(f"Task {self.task.id} failed: {error_msg}")
                self.finished.emit(STATUS_FAILED, "", (error_msg or "Download failed"))
        
        except Exception as e:
            logger.exception(f"Exception in download task {self.task.id}")
            self.finished.emit(STATUS_FAILED, "", str(e))
    
    def _build_spotify_command(self) -> list[str]:
        """Build command for Spotify download using spotdl."""
        cmd = [
            self.settings.spotdl_path,
            "download",
            self.task.url,
            "--output", self.settings.output_dir,
        ]
        
        # Add format if not mp3 (mp3 is default)
        if self.settings.default_format.lower() != "mp3":
            cmd.extend(["--format", self.settings.default_format])
        
        # Add bitrate if not "Best"
        if self.settings.default_quality != "Best":
            bitrate = self.settings.default_quality.replace("kbps", "k")
            cmd.extend(["--bitrate", bitrate])
        
        return cmd
    
    def _build_youtube_command(self) -> list[str]:
        """Build command for YouTube download using yt-dlp."""
        output_template = os.path.join(
            self.settings.output_dir,
            "%(title)s.%(ext)s"
        )
        
        cmd = [
            self.settings.yt_dlp_path,
            "-f", "ba",  # best audio
            "-x",  # extract audio
            "--audio-format", self.settings.default_format,
            "-o", output_template,
        ]
        
        # Add quality settings
        if self.settings.default_quality == "Best":
            cmd.extend(["--audio-quality", "0"])  # best VBR
        else:
            bitrate = self.settings.default_quality.replace("kbps", "k")
            cmd.extend(["--audio-quality", bitrate])
        
        # Add metadata options
        if self.settings.embed_metadata:
            cmd.append("--add-metadata")
        
        if self.settings.embed_thumbnail:
            cmd.append("--embed-thumbnail")
        
        # Add the URL or search query
        cmd.append(self.task.url)
        
        return cmd
    
    def _is_youtube_search(self, text: str) -> bool:
        """Check if text is a YouTube URL or search query."""
        from ..utils.validators import is_youtube_url
        return is_youtube_url(text) or text.startswith("ytsearch")
    
    def _execute_command(self, cmd: list[str]) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Execute download command and parse output.
        
        Returns:
            (success, output_file, error_message)
        """
        try:
            # Prepare environment for subprocess so spotdl sees Spotify credentials
            env = os.environ.copy()
            client_id = getattr(self.settings, "spotify_client_id", "")
            client_secret = getattr(self.settings, "spotify_client_secret", "")
            if client_id and client_secret:
                env["SPOTIPY_CLIENT_ID"] = client_id
                env["SPOTIPY_CLIENT_SECRET"] = client_secret

            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except FileNotFoundError:
            return (False, None, f"Command not found: {cmd[0]}")
        except Exception as e:
            return (False, None, f"Failed to start process: {str(e)}")
        
        output_lines = []
        output_file = None
        last_progress = 0
        
        # Apply a soft timeout based on settings to avoid hanging indefinitely
        timeout_seconds = getattr(self.settings, "timeout_seconds", 300) or 300
        try:
            timeout_seconds = int(timeout_seconds)
        except (TypeError, ValueError):
            timeout_seconds = 300
        timeout_seconds = max(30, min(timeout_seconds, 3600))
        start_time = time.time()
        
        while True:
            if self._should_cancel:
                if self._process.poll() is None:
                    self._process.terminate()
                return (False, None, "Cancelled by user")
            
            # Check for timeout (best-effort; assumes the process is still producing output)
            if timeout_seconds and (time.time() - start_time) > timeout_seconds:
                if self._process.poll() is None:
                    self._process.terminate()
                msg = f"Download timed out after {timeout_seconds} seconds"
                output_lines.append(f"SpotiPlay: {msg}\n")
                return (False, output_file, msg)
            
            line = self._process.stdout.readline() if self._process.stdout else ""
            
            if not line:
                if self._process.poll() is not None:
                    break
                continue
            
            output_lines.append(line)
            logger.debug(f"Task {self.task.id}: {line.rstrip()}")
            
            # Parse progress
            progress, speed, eta = self._parse_progress(line, last_progress)
            if progress != last_progress:
                last_progress = progress
                self.progress_updated.emit(progress, speed, eta)
            
            # Try to extract output filename
            if not output_file:
                file_match = re.search(r'\[download\] Destination: (.+)', line)
                if file_match:
                    output_file = file_match.group(1).strip()
                else:
                    # spotdl format
                    file_match = re.search(r'Downloaded "(.+)"', line)
                    if file_match:
                        output_file = file_match.group(1).strip()
        
        returncode = self._process.poll()
        
        if returncode == 0:
            self.progress_updated.emit(100, "", "")
            return (True, output_file, None)
        else:
            error_text = "\n".join(output_lines[-20:])  # Last 20 lines
            return (False, output_file, error_text)
    
    def _parse_progress(self, line: str, current: int) -> tuple[int, str, str]:
        """
        Parse progress information from output line.
        
        Returns:
            (progress, speed, eta)
        """
        # yt-dlp progress format: "[download]  45.2% of 3.24MiB at 1.23MiB/s ETA 00:02"
        progress_match = re.search(r'(\d+\.?\d*)%', line)
        if progress_match:
            try:
                progress = int(float(progress_match.group(1)))
                progress = max(current, min(100, progress))
                
                # Extract speed
                speed = ""
                speed_match = re.search(r'at\s+([\d.]+\s*[KMG]?i?B/s)', line)
                if speed_match:
                    speed = speed_match.group(1)
                
                # Extract ETA
                eta = ""
                eta_match = re.search(r'ETA\s+([\d:]+)', line)
                if eta_match:
                    eta = eta_match.group(1)
                
                return (progress, speed, eta)
            except ValueError:
                pass
        
        # spotdl progress (less detailed)
        if "Downloading" in line and current < 50:
            return (50, "", "")
        if "Converting" in line and current < 80:
            return (80, "", "")
        if "Downloaded" in line and current < 100:
            return (100, "", "")
        
        return (current, "", "")
    
    def _classify_error_message(self, raw_error: str) -> str:
        """Map low-level errors from spotdl/Spotify into a user-friendly message.

        This keeps messages short for the UI and highlights common Spotify issues
        like rate limits (HTTP 429).
        """
        text = (raw_error or "").strip()
        if not text:
            return "Download failed"

        lower = text.lower()

        # Spotify rate limiting / HTTP 429
        if "429 error responses" in lower or "rate/request limit" in lower or "max retries reached" in lower:
            return (
                "Spotify is rate-limiting your account (HTTP 429). "
                "Please wait a while (up to 24 hours) and reduce parallel downloads "
                "or the number of playlists you download at once."
            )

        # Generic network / provider errors
        if "audio providererror" in lower or "yt-dlp download error" in lower:
            return (
                "Audio download failed (yt-dlp error). This is often a temporary "
                "network/YouTube issue. Try again later."
            )

        if "connection error" in lower or "connection aborted" in lower or "timed out" in lower:
            return "Network error while contacting Spotify/YouTube. Please check your connection and try again."

        # Fallback: trim long stack traces
        if len(text) > 500:
            return text[:500] + "..."
        return text

    def _is_retryable_error(self, message: Optional[str]) -> bool:
        """Return True if the error looks transient and worth retrying."""
        if not message:
            return False

        lower = message.lower()

        # Rate limiting is usually long-lived (hours), so don't hammer Spotify with retries
        if "429" in lower or "rate-limit" in lower or "rate/request limit" in lower:
            return False

        # Network-ish errors are typically retryable
        retry_keywords = [
            "network error",
            "timed out",
            "temporarily unavailable",
            "connection aborted",
            "connection reset",
            "yt-dlp download error",
            "audio providererror",
        ]

        return any(key in lower for key in retry_keywords)
