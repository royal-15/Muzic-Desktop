"""Resolve YouTube playlist URLs into individual video URLs."""
import subprocess
import time
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal


@dataclass
class PlaylistResolution:
    """Result of resolving one playlist URL."""
    playlist_url: str
    video_urls: list[str]
    error: str = ""


class PlaylistResolver(QThread):
    """Resolve playlists off the UI thread using yt-dlp's flat listing mode."""

    resolved = Signal(object)

    def __init__(self, queries: list[str], yt_dlp_path: str, timeout_seconds: int = 300, parent=None):
        super().__init__(parent)
        self.queries = queries
        self.yt_dlp_path = yt_dlp_path
        self.timeout_seconds = timeout_seconds

    def run(self) -> None:
        results = []
        for query in self.queries:
            if not self._is_playlist_url(query):
                results.append((query, None))
                continue
            results.append((query, self._resolve(query)))
        self.resolved.emit(results)

    @staticmethod
    def _is_playlist_url(url: str) -> bool:
        from .url_parser import URLParser
        return URLParser.is_playlist(url)

    def _resolve(self, url: str) -> PlaylistResolution:
        try:
            timeout_seconds = max(30, int(self.timeout_seconds or 300))
        except (TypeError, ValueError):
            timeout_seconds = 300
        command = [
            self.yt_dlp_path,
            "--flat-playlist",
            "--print",
            "%(webpage_url)s",
            url,
        ]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            deadline = time.monotonic() + timeout_seconds
            while True:
                if self.isInterruptionRequested():
                    process.terminate()
                    process.communicate()
                    return PlaylistResolution(url, [], "Playlist resolution cancelled")
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic() >= deadline:
                        process.terminate()
                        stdout, stderr = process.communicate()
                        return PlaylistResolution(url, [], "Playlist resolution timed out")
        except FileNotFoundError:
            return PlaylistResolution(url, [], f"Command not found: {self.yt_dlp_path}")
        except (OSError, ValueError) as error:
            return PlaylistResolution(url, [], f"Could not resolve playlist: {error}")

        video_urls = []
        seen = set()
        for line in stdout.splitlines():
            video_url = line.strip()
            if video_url.startswith(("https://", "http://")) and video_url not in seen:
                seen.add(video_url)
                video_urls.append(video_url)

        if process.returncode != 0:
            details = stderr.strip().splitlines()
            error = details[-1] if details else f"yt-dlp exited with code {process.returncode}"
            return PlaylistResolution(url, [], error)
        if not video_urls:
            return PlaylistResolution(url, [], "No song URLs were found in this playlist")
        return PlaylistResolution(url, video_urls)
