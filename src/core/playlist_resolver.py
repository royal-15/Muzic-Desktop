"""Resolve YouTube playlist URLs into individual video URLs."""
import time
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


@dataclass
class PlaylistResolution:
    """Result of resolving one playlist URL."""

    playlist_url: str
    video_urls: list[str]
    error: str = ""
    video_titles: list[str] = field(default_factory=list)
    existing_files: dict[str, str] = field(default_factory=dict)


class PlaylistResolver(QThread):
    """Resolve playlists off the UI thread using bundled yt-dlp."""

    resolved = Signal(object)

    def __init__(self, queries: list[str], timeout_seconds: int = 300, output_dir: str = "", audio_format: str = "mp3", ffmpeg_path: str = "", parent=None):
        super().__init__(parent)
        self.queries = queries
        self.output_dir = output_dir
        self.audio_format = audio_format
        self.ffmpeg_path = ffmpeg_path
        try:
            self.timeout_seconds = max(30, min(int(timeout_seconds or 300), 3600))
        except (TypeError, ValueError):
            self.timeout_seconds = 300
        self._current_url = ""
        self._deadline = 0.0

    def run(self) -> None:
        results = []
        for query in self.queries:
            if self.isInterruptionRequested():
                break
            if not self._is_playlist_url(query):
                results.append((query, None))
                continue
            results.append((query, self._resolve(query)))
        self.resolved.emit(results)

    @staticmethod
    def _is_playlist_url(url: str) -> bool:
        from .url_parser import URLParser
        return URLParser.is_playlist(url)

    def _check_interruption(self, _data: dict) -> None:
        if self.isInterruptionRequested():
            raise DownloadError("Playlist resolution cancelled")
        if time.monotonic() > self._deadline:
            raise DownloadError("Playlist resolution timed out")

    def _resolve(self, url: str) -> PlaylistResolution:
        self._current_url = url
        self._deadline = time.monotonic() + self.timeout_seconds
        options = {
            "extract_flat": "in_playlist",
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "socket_timeout": self.timeout_seconds,
            "progress_hooks": [self._check_interruption],
        }
        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
        except DownloadError as error:
            message = str(error).strip()
            if self.isInterruptionRequested():
                message = "Playlist resolution cancelled"
            elif "timed out" in message.lower():
                message = "Playlist resolution timed out"
            return PlaylistResolution(url, [], message or "Could not resolve playlist")
        except Exception as error:
            return PlaylistResolution(url, [], f"Could not resolve playlist: {error}")

        if isinstance(info, dict):
            entries = info.get("entries")
            if entries is None:
                entries = [info]
        else:
            entries = []
        video_urls = []
        video_titles = []
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            video_url = entry.get("webpage_url") or entry.get("url")
            if video_url and not video_url.startswith(("http://", "https://")):
                video_id = entry.get("id") or video_url
                video_url = f"https://www.youtube.com/watch?v={video_id}"
            if video_url and video_url not in seen:
                seen.add(video_url)
                video_urls.append(video_url)
                video_titles.append(str(entry.get("title") or entry.get("id") or ""))

        if not video_urls:
            return PlaylistResolution(url, [], "No song URLs were found in this playlist")
        existing_files = {}
        for video_url, title in zip(video_urls, video_titles):
            if title:
                output_file = self._valid_existing_file(title)
                if output_file:
                    existing_files[video_url] = output_file
        return PlaylistResolution(url, video_urls, video_titles=video_titles, existing_files=existing_files)

    def _valid_existing_file(self, title: str) -> str:
        """Return the expected playlist output when it exists and decodes cleanly."""
        from yt_dlp.utils import sanitize_filename

        safe_title = sanitize_filename(title, restricted=False)
        candidate = Path(self.output_dir) / f"{safe_title}.{self.audio_format}"
        if not candidate.is_file() or candidate.stat().st_size <= 0:
            return ""

        ffmpeg = self.ffmpeg_path or "ffmpeg"
        if os.path.isdir(ffmpeg):
            executable = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
            ffmpeg = os.path.join(ffmpeg, executable)
        elif os.path.basename(ffmpeg).lower() in {"ffmpeg.exe", "ffmpeg"}:
            ffmpeg = shutil.which(ffmpeg) or shutil.which("ffmpeg") or ffmpeg
        try:
            result = subprocess.run(
                [ffmpeg, "-v", "error", "-xerror", "-i", str(candidate), "-f", "null", "-"],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return str(candidate) if result.returncode == 0 else ""
