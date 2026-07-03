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
- `ffmpeg` — audio conversion

**Build a standalone executable (PyInstaller):**
```bash
pip install pyinstaller
pyinstaller Muzic.spec
# Or manually:
pyinstaller --name="Muzic" --windowed --onefile \
            --add-data="src:src" \
            --add-data="resources:resources" \
            --hidden-import=PySide6 \
            run.py
```

There are no automated tests in this project.

## Architecture

### Entry point and startup flow
`run.py` -> `src/main.py:main()` creates a `QApplication`, instantiates `MainWindow`, and calls `app.exec()`. `MainWindow.__init__` loads settings, initializes `Theme` and `DownloadManager`, builds the UI, and shows a first-run disclaimer dialog if needed.

### Configuration (`src/config/`)
- `constants.py` — app-wide constants: paths (`CONFIG_FILE`, `LOG_FILE`), status strings, color palettes (`COLORS_DARK`/`COLORS_LIGHT`), UI sizing, and YouTube URL patterns.
- `settings.py` — `AppSettings` is a `@dataclass` serialized to/from `config.json` in the project root. `SettingsManager` is a singleton that owns the single `AppSettings` instance; all UI code accesses settings through it. Settings loading ignores unknown legacy keys from older configs.

### Download engine (`src/core/`)
- `download_worker.py` — `DownloadTask` is a plain `@dataclass` (id, url, status, progress, speed, eta, output_file, error_message). `DownloadWorker(QThread)` runs `yt-dlp` as a subprocess, passing FFmpeg via `--ffmpeg-location`, parsing stdout for progress, retrying transient failures with exponential backoff, and classifying common YouTube/network/FFmpeg errors into user-friendly messages. Plain text is converted to `ytsearch1:` before invoking `yt-dlp`.
- `download_manager.py` — `DownloadManager(QObject)` owns `_tasks: Dict[int, DownloadTask]` and `_workers: Dict[int, DownloadWorker]`. It enforces `settings.max_parallel_downloads` by calling `_try_start_next_task()` after every task finishes. Emits Qt signals (`task_added`, `task_updated`, `task_completed`, `task_failed`, `queue_changed`) that `MainWindow` connects to for UI updates.
- `url_parser.py` — `URLParser.parse(url)` returns a `URLInfo` dataclass with YouTube source/type/id information. Used for display-oriented parsing.

### UI (`src/ui/`)
- `main_window.py` — Single file containing `MainWindow`, `SettingsDialog`, and `ManagePlaylistsDialog`. `MainWindow` holds the queue display, input controls, quality/format selectors, output directory controls, and saved YouTube playlist folder mappings. `_process_query()` converts raw input + mode into YouTube URLs or `ytsearch1:` search strings before handing off to `DownloadManager`. `From .txt` mode reads one URL or song name per non-empty line.
- `styles/theme.py` — `Theme` generates a complete Qt Style Sheet (QSS) string from `COLORS_DARK`/`COLORS_LIGHT` at runtime. Button variants are styled via Qt object names: `secondaryButton`, `dangerButton`.
- `components/toast.py` — `Toast(QLabel)` is a frameless overlay widget with fade-in/out `QPropertyAnimation`. Use `Toast.show_message(parent, message, type, duration_ms)` for notifications throughout the UI.

### Utilities (`src/utils/`)
- `logger.py` — Singleton `Logger` wrapping Python's `logging`. Writes DEBUG+ to `muzic.log`, INFO+ to stdout. Import via `from ..utils.logger import logger`.
- `validators.py` — URL detection helpers (`is_youtube_url`), `parse_multiple_urls` (splits by newline/comma/semicolon/space), directory validation, and filename sanitization.

### Persistent state files (project root)
| File | Purpose |
|---|---|
| `config.json` | App settings |
| `muzic.log` | Runtime log |
| `history.json` | Download history (path defined but not yet implemented) |
