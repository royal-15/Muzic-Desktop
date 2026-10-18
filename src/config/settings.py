"""Configuration management with JSON persistence."""
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field, fields, asdict

from .constants import (
    CONFIG_FILE,
    APP_DIR,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_MAX_PARALLEL,
    DEFAULT_QUALITY,
    DEFAULT_FORMAT,
    DEFAULT_THEME,
    DEFAULT_FFMPEG,
)


@dataclass
class AppSettings:
    """Application settings with JSON serialization."""
    
    # General settings
    output_dir: str = field(default=DEFAULT_OUTPUT_DIR)
    theme: str = field(default=DEFAULT_THEME)

    # Playlist folder mappings: playlist name -> folder path
    playlist_folders: dict[str, str] = field(default_factory=dict)

    # Optional playlist URL mappings: playlist name -> playlist URL
    playlist_urls: dict[str, str] = field(default_factory=dict)
    
    # Download settings
    default_quality: str = field(default=DEFAULT_QUALITY)
    default_format: str = field(default=DEFAULT_FORMAT)
    max_parallel_downloads: int = field(default=DEFAULT_MAX_PARALLEL)
    retry_attempts: int = field(default=3)
    timeout_seconds: int = field(default=300)
    
    # Tool paths
    # Retained so older config.json files still load; yt-dlp is bundled now.
    yt_dlp_path: str = field(default="yt-dlp")
    ffmpeg_path: str = field(default=DEFAULT_FFMPEG)
    deno_path: str = field(default="")
    # Use Deno for fuller YouTube challenge support when it is available.
    use_deno_runtime: bool = field(default=False)

    # YouTube authentication metadata only; cookie values are never stored here.
    youtube_auth_mode: str = field(default="none")
    # Retained for old config files; browser mode now detects the OS default.
    youtube_browser: str = field(default="chrome")
    youtube_cookies_file: str = field(default="")
    
    # UI preferences
    window_width: int = field(default=1000)
    window_height: int = field(default=700)
    window_maximized: bool = field(default=False)
    
    # Advanced settings
    use_proxy: bool = field(default=False)
    proxy_url: str = field(default="")
    embed_metadata: bool = field(default=True)
    embed_thumbnail: bool = field(default=True)
    custom_filename_template: str = field(default="")
    
    # First run
    disclaimer_accepted: bool = field(default=False)
    first_run: bool = field(default=True)
    
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AppSettings":
        """Load settings from JSON and ignore settings from older releases."""
        config_path = path or CONFIG_FILE
        if path is None and not config_path.exists():
            legacy_path = APP_DIR / "config.json"
            if legacy_path.is_file():
                config_path = legacy_path
        
        if not config_path.exists():
            return cls()
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            valid_keys = {item.name for item in fields(cls)}
            clean_data = {
                key: value
                for key, value in data.items()
                if key in valid_keys
            }
            settings = cls(**clean_data)
        except (json.JSONDecodeError, TypeError, ValueError):
            # Return defaults if config is corrupted
            settings = cls()
        
        return settings
    
    def save(self, path: Optional[Path] = None) -> bool:
        """Save settings to JSON file."""
        config_path = path or CONFIG_FILE
        
        try:
            # Ensure parent directory exists
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            valid, _ = self.validate()
            if not valid:
                return False
            fd, temporary_path = tempfile.mkstemp(prefix="config-", suffix=".tmp", dir=config_path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(asdict(self), f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporary_path, config_path)
            finally:
                if os.path.exists(temporary_path):
                    os.unlink(temporary_path)
            return True
        except (OSError, IOError) as e:
            print(f"Failed to save settings: {e}")
            return False
    
    def update(self, **kwargs: Any) -> None:
        """Update settings with provided keyword arguments."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def validate(self) -> tuple[bool, list[str]]:
        """Validate settings and return (is_valid, error_messages)."""
        errors = []
        
        # Validate output directory
        if not isinstance(self.output_dir, str) or not self.output_dir.strip():
            errors.append("Output directory cannot be empty")
        if not isinstance(self.default_quality, str) or self.default_quality not in {"Best", "320kbps", "256kbps", "192kbps", "128kbps"}:
            errors.append("Choose a supported audio quality")
        if not isinstance(self.default_format, str) or self.default_format not in {"mp3", "m4a", "flac", "wav"}:
            errors.append("Choose a supported audio format")
        if not isinstance(self.playlist_folders, dict) or not isinstance(self.playlist_urls, dict):
            errors.append("Playlist mappings must be valid name and path mappings")
        
        # Validate parallel downloads
        if not isinstance(self.max_parallel_downloads, int) or isinstance(self.max_parallel_downloads, bool) or not 1 <= self.max_parallel_downloads <= 10:
            errors.append("Max parallel downloads must be between 1 and 10")
        
        # Validate retry attempts
        if not isinstance(self.retry_attempts, int) or isinstance(self.retry_attempts, bool) or not 0 <= self.retry_attempts <= 10:
            errors.append("Retry attempts must be between 0 and 10")
        
        # Validate timeout
        if not isinstance(self.timeout_seconds, int) or isinstance(self.timeout_seconds, bool) or not 30 <= self.timeout_seconds <= 3600:
            errors.append("Timeout must be between 30 and 3600 seconds")

        if not isinstance(self.ffmpeg_path, str):
            errors.append("FFmpeg path must be text")
        if self.youtube_auth_mode not in {"none", "browser", "file"}:
            errors.append("Choose a supported YouTube authentication source")
        if not isinstance(self.youtube_browser, str) or not isinstance(self.youtube_cookies_file, str):
            errors.append("YouTube authentication settings must be text")
        elif self.youtube_auth_mode == "file" and not self.youtube_cookies_file.strip():
            errors.append("Choose a Netscape-format YouTube cookies file")
        if not isinstance(self.deno_path, str):
            errors.append("Deno path must be text")
        if not isinstance(self.use_deno_runtime, bool):
            errors.append("JavaScript runtime preference must be a boolean")
        
        return (len(errors) == 0, errors)
    
    def reset_to_defaults(self) -> None:
        """Reset all settings to default values."""
        defaults = AppSettings()
        for key, value in asdict(defaults).items():
            setattr(self, key, value)


class SettingsManager:
    """Singleton manager for application settings."""
    
    _instance: Optional["SettingsManager"] = None
    _settings: Optional[AppSettings] = None
    
    def __new__(cls) -> "SettingsManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @property
    def settings(self) -> AppSettings:
        """Get current settings, loading from disk if necessary."""
        if self._settings is None:
            self._settings = AppSettings.load()
        return self._settings
    
    def reload(self) -> None:
        """Reload settings from disk."""
        self._settings = AppSettings.load()
    
    def save(self) -> bool:
        """Save current settings to disk."""
        if self._settings is not None:
            return self._settings.save()
        return False
    
    def update(self, **kwargs: Any) -> None:
        """Update and save settings."""
        self.settings.update(**kwargs)
        self.save()
