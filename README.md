# Muzic v2.0.3 - Modern Music Downloader

Muzic is a PySide6 desktop app for downloading audio from YouTube videos, YouTube playlists, and YouTube search results. It uses `yt-dlp` for downloads and FFmpeg for audio extraction/conversion.

## Key Features

- **YouTube audio downloads**: Download from videos, playlists, or song-name searches.
- **Batch text input**: Use `From .txt` mode to queue one YouTube URL or song name per line.
- **Queue system**: Add multiple downloads and let the app run them automatically.
- **Parallel downloads**: Configure up to 10 simultaneous downloads.
- **Progress tracking**: View progress, speed, and ETA for each task.
- **Quality and format controls**: Choose quality presets and MP3, M4A, FLAC, or WAV output.
- **Playlist folders**: Save destination folders for playlists and select them from the playlist menu.
- **Existing-file checks**: After a playlist is resolved, valid tracks already in its destination are marked completed. Missing, incomplete, or invalid tracks are downloaded again.
- **Bundled downloader**: yt-dlp is included in the app; configure the FFmpeg executable path in Settings.

## Installation

### Prerequisites

- Python 3.14.6
- FFmpeg

### Quick Start

```bash
git clone https://github.com/yourusername/Muzic-Desktop.git
cd Muzic-Desktop
python -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
python run.py
```

Download FFmpeg from https://ffmpeg.org/download.html or configure its path in Settings.

## Usage

1. Launch the app with `python run.py`.
2. Choose an input mode:
   - `Auto`: accepts YouTube URLs or searches YouTube for plain text.
   - `YouTube URL`: accepts only YouTube video or playlist URLs.
   - `Search on YouTube`: treats input as a song-name search.
   - `From .txt`: reads one YouTube URL or song name per non-empty line from a text file.
3. Select output directory, quality, and format. You can save a playlist-specific destination with `Save Playlist Folder` and select it later from the playlist menu.
4. Click `Add to Queue`. Resolved playlists are checked against the destination folder using the selected output format. Existing audio files are validated with FFmpeg; valid files are marked completed, and missing or invalid files are queued for download.

Downloads start automatically and respect the configured max parallel download limit.

## Supported Input

- YouTube videos: `https://www.youtube.com/watch?v=...`
- YouTube short links: `https://youtu.be/...`
- YouTube playlists: `https://www.youtube.com/playlist?list=...`
- Song names: `Imagine Dragons Believer`
- `.txt` batch files with one URL or search name per line

## Project Structure

```text
Muzic-Desktop/
├── src/
│   ├── config/
│   ├── core/
│   ├── ui/
│   └── utils/
├── requirements.txt
├── run.py
└── README.md
```

## Building Executable

Build each release artifact on its target operating system using Python 3.14.6. PyInstaller does not create one executable that runs on both Windows and Linux: build the Windows `.exe` on Windows and the Linux executable on Linux. The spec names outputs with the version, platform, and architecture, and bundles yt-dlp. FFmpeg is an external runtime dependency and is not included.

### Windows x64

From PowerShell at the repository root:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt -r requirements-build.txt
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
pyinstaller --clean --noconfirm Muzic.spec
```

This produces `dist/Muzic-2.0.3-windows-x64.exe`. Run it and confirm the main window opens. Check that yt-dlp is bundled and FFmpeg is absent:

```powershell
pyi-archive_viewer -l dist\Muzic-2.0.3-windows-x64.exe | Select-String -Pattern 'yt_dlp|ffmpeg'
```

### Linux x64

From a Linux shell at the repository root:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt -r requirements-build.txt
rm -rf build dist
pyinstaller --clean --noconfirm Muzic.spec
```

This produces `dist/Muzic-2.0.3-linux-x64` (no `.exe` suffix). Run it and confirm the main window opens. Check that yt-dlp is bundled and FFmpeg is absent:

```bash
pyi-archive_viewer -l dist/Muzic-2.0.3-linux-x64 | grep -Ei 'yt_dlp|ffmpeg'
```

The archive listing should contain yt-dlp modules and no FFmpeg executable. Do not add FFmpeg to `binaries` or `datas` in `Muzic.spec`.

## Manual GitHub Release Flow

1. Update the app version, this README's release examples, and the changelog, then commit the release changes.
2. Create and push a matching version tag, for example `v2.0.3`.
3. Follow the Windows x64 and Linux x64 build steps above on their respective operating systems. Smoke-check each artifact and verify its archive contains no FFmpeg.
4. Create a GitHub Release for that tag and attach `Muzic-2.0.3-windows-x64.exe` and `Muzic-2.0.3-linux-x64`, plus the separately distributed FFmpeg archive(s). Never put FFmpeg inside a Muzic executable.
5. In the release notes, state the supported FFmpeg version, link to its upstream source, and explain that users must install it or set its path in Muzic Settings. Include brief upgrade notes and a summary of changes.

Users can download FFmpeg from https://ffmpeg.org/download.html or use the separately provided release asset, then configure its executable path in Settings.

## Release Assets

Use clear names that include the app version, platform, and architecture: `Muzic-2.0.3-windows-x64.exe` and `Muzic-2.0.3-linux-x64`. These are separate native builds and each runs only on its matching platform. Keep separately distributed FFmpeg archives clearly versioned and identify their upstream source and version in the release notes. Verify the FFmpeg distribution's license and redistribution terms before attaching them.

## Building from Source

For development, install the app dependencies and launch it directly:

```bash
pip install -r requirements.txt
python run.py
```

## Disclaimer

This application is for educational purposes only. Users are responsible for ensuring they have the legal right to download any content. Downloading copyrighted material without permission may violate copyright laws and terms of service.

## License

This project is provided as-is for educational purposes.

**Version**: 2.0.3
**Author**: Muzic Team
