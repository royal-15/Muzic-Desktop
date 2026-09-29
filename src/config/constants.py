"""Application constants and configuration values."""
from pathlib import Path
import sys

# Application info
APP_NAME = "Muzic"
APP_VERSION = "2.0.1"
APP_AUTHOR = "Muzic Team"
APP_DESCRIPTION = "Modern Music Downloader"

# File paths
if getattr(sys, "frozen", False):
    # Running as compiled executable
    BASE_DIR = Path(sys._MEIPASS)  # type: ignore
    APP_DIR = Path(sys.executable).parent
else:
    # Running as script
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    APP_DIR = BASE_DIR

CONFIG_FILE = APP_DIR / "config.json"
HISTORY_FILE = APP_DIR / "history.json"
LOG_FILE = APP_DIR / "muzic.log"

# Resource paths
RESOURCES_DIR = BASE_DIR / "resources"
ICONS_DIR = RESOURCES_DIR / "icons"
LOGO_PATH = RESOURCES_DIR / "logo.ico"

# Default settings
DEFAULT_OUTPUT_DIR = str(Path.home() / "Downloads" / "Muzic")
DEFAULT_MAX_PARALLEL = 3
DEFAULT_QUALITY = "320kbps"
DEFAULT_FORMAT = "mp3"
DEFAULT_THEME = "dark"

# Quality options
QUALITY_OPTIONS = ["Best", "320kbps", "256kbps", "192kbps", "128kbps"]

# Format options
FORMAT_OPTIONS = ["mp3", "m4a", "flac", "wav"]

# Download status
STATUS_QUEUED = "queued"
STATUS_DOWNLOADING = "downloading"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_PAUSED = "paused"
STATUS_CANCELLED = "cancelled"

# UI Constants
WINDOW_MIN_WIDTH = 900
WINDOW_MIN_HEIGHT = 600
WINDOW_DEFAULT_WIDTH = 1000
WINDOW_DEFAULT_HEIGHT = 700

# Color palette (Dark theme)
COLORS_DARK = {
    "primary": "#14B8A6",
    "background": "#121212",
    "surface": "#1E1E1E",
    "card": "#282828",
    "card_hover": "#323232",
    "text_primary": "#FFFFFF",
    "text_secondary": "#B3B3B3",
    "text_disabled": "#666666",
    "success": "#22C55E",
    "warning": "#FFA726",
    "error": "#EF5350",
    "info": "#42A5F5",
    "border": "#404040",
    "input_bg": "#2A2A2A",
}

# Color palette (Light theme)
COLORS_LIGHT = {
    "primary": "#0D9488",
    "background": "#FFFFFF",
    "surface": "#F5F5F5",
    "card": "#FFFFFF",
    "card_hover": "#F8F8F8",
    "text_primary": "#000000",
    "text_secondary": "#666666",
    "text_disabled": "#AAAAAA",
    "success": "#16A34A",
    "warning": "#FF9800",
    "error": "#F44336",
    "info": "#2196F3",
    "border": "#E0E0E0",
    "input_bg": "#FAFAFA",
}

# Font settings
FONT_FAMILY = "Segoe UI, SF Pro Display, Roboto, sans-serif"
FONT_SIZE_TITLE = 20
FONT_SIZE_SUBTITLE = 16
FONT_SIZE_BODY = 14
FONT_SIZE_CAPTION = 12

# Spacing
SPACING_UNIT = 8
PADDING = SPACING_UNIT * 2
MARGIN = SPACING_UNIT
BORDER_RADIUS = 8

# Animation durations (ms)
ANIMATION_FAST = 150
ANIMATION_MEDIUM = 300
ANIMATION_SLOW = 500

YOUTUBE_PATTERNS = [
    r"^https?://((www|m|music)\.)?(youtube\.com|youtu\.be)/",
]
