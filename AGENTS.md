# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Commands

**Run the app:**
```bash
python run.py
```

**Install dependencies (Python 3.12 required):**
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**External tool dependencies** (must be available on PATH or configured in Settings):
- `yt-dlp` — YouTube downloads
- `spotdl` — Spotify downloads
- `ffmpeg` — audio conversion

**Build a standalone executable (PyInstaller):**
```bash
pip install pyinstaller
pyinstaller SpotiPlay.spec
# Or manually:
pyinstaller --name="SpotiPlay" --windowed --onefile \
            --add-data="src:src" \
            --add-data="resources:resources" \
            --hidden-import=PySide6 \
            run.py
```

There are no automated tests in this project.

## Architecture

### Entry point and startup flow
`run.py` → `src/main.py:main()` creates a `QApplication`, instantiates `MainWindow`, and calls `app.exec()`. `MainWindow.__init__` loads settings, initializes `Theme` and `DownloadManager`, builds the UI, and shows a first-run disclaimer dialog if needed.

### Configuration (`src/config/`)
- `constants.py` — app-wide constants: paths (`CONFIG_FILE`, `LOG_FILE`, `ENV_FILE`), status strings, color palettes (`COLORS_DARK`/`COLORS_LIGHT`), UI sizing, and URL regex patterns.
- `settings.py` — `AppSettings` is a `@dataclass` serialized to/from `config.json` in the project root. `SettingsManager` is a singleton that owns the single `AppSettings` instance; all UI code accesses settings through it. **Spotify API credentials** are kept out of `config.json` and instead persisted to `.env` (git-ignored) via `save_spotify_credentials_to_env()`. On load, `AppSettings._load_spotify_from_env()` reads `.env` or the `SPOTIPY_CLIENT_ID`/`SPOTIPY_CLIENT_SECRET` env vars and merges them in, then propagates them to the process environment so child `spotdl` processes see them.

### Download engine (`src/core/`)
- `download_worker.py` — `DownloadTask` is a plain `@dataclass` (id, url, status, progress, speed, eta, output_file, error_message). `DownloadWorker(QThread)` takes a task and runs `yt-dlp` or `spotdl` as a subprocess, parsing stdout line-by-line for progress (`%` patterns for yt-dlp; keyword heuristics for spotdl). It implements retry with exponential backoff, a configurable timeout, and classifies common errors (Spotify rate-limiting HTTP 429, network failures) into user-friendly messages. URL routing: Spotify URLs → `spotdl download`, YouTube URLs → `yt-dlp -x`, plain text → spotdl search or `ytsearch1:` prefix for yt-dlp.
- `download_manager.py` — `DownloadManager(QObject)` owns `_tasks: Dict[int, DownloadTask]` and `_workers: Dict[int, DownloadWorker]`. It enforces `settings.max_parallel_downloads` by calling `_try_start_next_task()` after every task finishes. Emits Qt signals (`task_added`, `task_updated`, `task_completed`, `task_failed`, `queue_changed`) that `MainWindow` connects to for UI updates.
- `url_parser.py` — `URLParser.parse(url)` returns a `URLInfo` dataclass with `source`, `type` (track/album/playlist/video/channel), and extracted `id`. Used for display purposes; routing logic is duplicated in `download_worker.py`.

### UI (`src/ui/`)
- `main_window.py` — Single file containing `MainWindow`, `SettingsDialog`, and `ManagePlaylistsDialog`. `MainWindow` holds all queue state display (a `QTableWidget` rebuilt on every `queue_changed` signal), input controls (URL field, mode combo, quality/format selectors), and a playlist folder mapping system. Playlist folders + URLs are stored as dicts in `AppSettings` (`playlist_folders`, `playlist_urls`); selecting a saved playlist auto-fills the output directory and URL input. `_process_query()` converts the raw input + mode into a list of URLs/search strings before handing off to `DownloadManager`.
- `styles/theme.py` — `Theme` generates a complete Qt Style Sheet (QSS) string from `COLORS_DARK`/`COLORS_LIGHT` at runtime. Button variants are styled via Qt object names: `secondaryButton`, `dangerButton`.
- `components/toast.py` — `Toast(QLabel)` is a frameless overlay widget with fade-in/out `QPropertyAnimation`. Use `Toast.show_message(parent, message, type, duration_ms)` for notifications throughout the UI.

### Utilities (`src/utils/`)
- `logger.py` — Singleton `Logger` wrapping Python's `logging`. Writes DEBUG+ to `spotiplay.log`, INFO+ to stdout. Import via `from ..utils.logger import logger`.
- `validators.py` — URL detection helpers (`is_spotify_url`, `is_youtube_url`), `parse_multiple_urls` (splits by newline/comma/semicolon), directory validation, and filename sanitization.

### Persistent state files (project root, git-ignored)
| File | Purpose |
|---|---|
| `config.json` | All app settings except Spotify credentials |
| `.env` | `SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET` |
| `spotiplay.log` | Runtime log |
| `history.json` | Download history (path defined but not yet implemented) |
