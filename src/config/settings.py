"""Configuration management with JSON persistence."""
import json
import os
from pathlib import Path
from typing import Any, Optional, Dict
from dataclasses import dataclass, field, asdict

from .constants import (
    CONFIG_FILE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_MAX_PARALLEL,
    DEFAULT_QUALITY,
    DEFAULT_FORMAT,
    DEFAULT_THEME,
    ENV_FILE,
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
    yt_dlp_path: str = field(default="yt-dlp")
    spotdl_path: str = field(default="spotdl")
    ffmpeg_path: str = field(default="ffmpeg")

    # Spotify API credentials (optional)
    # Used by spotdl/Spotify API to reduce rate limiting.
    spotify_client_id: str = field(default="")
    spotify_client_secret: str = field(default="")
    spotify_credentials_configured: bool = field(default=False)
    
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
        """Load settings from JSON file and merge in environment-based overrides."""
        config_path = path or CONFIG_FILE
        
        if not config_path.exists():
            settings = cls()
            settings._load_spotify_from_env()
            return settings
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            settings = cls(**data)
        except (json.JSONDecodeError, TypeError, ValueError):
            # Return defaults if config is corrupted
            settings = cls()
        
        # Merge Spotify credentials from .env / environment
        settings._load_spotify_from_env()
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

    # ----- Internal helpers for Spotify credentials -----

    def _load_spotify_from_env(self) -> None:
        """Populate Spotify credentials from .env / environment if available.

        This keeps sensitive values out of the JSON config while still exposing
        them via the settings object.
        """
        env_vars = _read_env_file()

        # Prefer explicit SPOTIPY_* env vars, then fall back to .env entries
        client_id = os.getenv("SPOTIPY_CLIENT_ID") or env_vars.get("SPOTIPY_CLIENT_ID", "")
        client_secret = os.getenv("SPOTIPY_CLIENT_SECRET") or env_vars.get("SPOTIPY_CLIENT_SECRET", "")

        if client_id and client_secret:
            self.spotify_client_id = client_id
            self.spotify_client_secret = client_secret
            self.spotify_credentials_configured = True

            # Ensure process environment has them set for any child processes
            os.environ["SPOTIPY_CLIENT_ID"] = client_id
            os.environ["SPOTIPY_CLIENT_SECRET"] = client_secret


def _read_env_file() -> Dict[str, str]:
    """Read key=value pairs from the local .env file.

    Very small helper so we don't need an external dependency like python-dotenv.
    """
    env_data: Dict[str, str] = {}

    if not ENV_FILE.exists():
        return env_data

    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    env_data[key] = value
    except OSError:
        # Ignore env read failures and just return what we have
        return env_data

    return env_data


def save_spotify_credentials_to_env(client_id: str, client_secret: str) -> None:
    """Persist Spotify client ID/secret to .env and update process env.

    The .env file is already ignored by git (.gitignore), so credentials stay
    local to the machine.
    """
    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()

    # Load current env file content so we don't clobber unrelated keys
    env_data = _read_env_file()

    if client_id and client_secret:
        env_data["SPOTIPY_CLIENT_ID"] = client_id
        env_data["SPOTIPY_CLIENT_SECRET"] = client_secret
    else:
        # If either is empty, remove both to avoid half-configured state
        env_data.pop("SPOTIPY_CLIENT_ID", None)
        env_data.pop("SPOTIPY_CLIENT_SECRET", None)

    try:
        lines = [f"{key}={value}\n" for key, value in env_data.items()]
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except OSError:
        # Fail silently; worst case spotdl just won't see credentials
        return

    # Reflect in current process env so new downloads see updated values
    if client_id and client_secret:
        os.environ["SPOTIPY_CLIENT_ID"] = client_id
        os.environ["SPOTIPY_CLIENT_SECRET"] = client_secret
    else:
        os.environ.pop("SPOTIPY_CLIENT_ID", None)
        os.environ.pop("SPOTIPY_CLIENT_SECRET", None)


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
