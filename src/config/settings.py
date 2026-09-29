"""Configuration management with JSON persistence."""
import json
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field, fields, asdict

from .constants import (
    CONFIG_FILE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_MAX_PARALLEL,
    DEFAULT_QUALITY,
    DEFAULT_FORMAT,
    DEFAULT_THEME,
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
    ffmpeg_path: str = field(default="ffmpeg.exe")
    
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
            
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2)
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
        if not self.output_dir:
            errors.append("Output directory cannot be empty")
        
        # Validate parallel downloads
        if self.max_parallel_downloads < 1 or self.max_parallel_downloads > 10:
            errors.append("Max parallel downloads must be between 1 and 10")
        
        # Validate retry attempts
        if self.retry_attempts < 0 or self.retry_attempts > 10:
            errors.append("Retry attempts must be between 0 and 10")
        
        # Validate timeout
        if self.timeout_seconds < 30 or self.timeout_seconds > 3600:
            errors.append("Timeout must be between 30 and 3600 seconds")
        
        # Validate proxy URL if enabled
        if self.use_proxy and not self.proxy_url:
            errors.append("Proxy URL is required when proxy is enabled")
        
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
