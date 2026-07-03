# Muzic v2.0 - Modern Music Downloader

Muzic is a PySide6 desktop app for downloading audio from YouTube videos, YouTube playlists, and YouTube search results. It uses `yt-dlp` for downloads and FFmpeg for audio extraction/conversion.

## Key Features

- **YouTube audio downloads**: Download from videos, playlists, or song-name searches.
- **Batch text input**: Use `From .txt` mode to queue one YouTube URL or song name per line.
- **Queue system**: Add multiple downloads and let the app run them automatically.
- **Parallel downloads**: Configure up to 10 simultaneous downloads.
- **Progress tracking**: View progress, speed, and ETA for each task.
- **Quality and format controls**: Choose quality presets and MP3, M4A, FLAC, or WAV output.
- **Configurable tools**: Set custom paths for `yt-dlp` and FFmpeg.

## Installation

### Prerequisites

- Python 3.12
- `yt-dlp`
- FFmpeg

### Quick Start

```bash
git clone https://github.com/yourusername/Muzic-Desktop.git
cd Muzic-Desktop
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py
```

Install external tools if they are not already available on `PATH`:

```bash
pip install yt-dlp
```

Download FFmpeg from https://ffmpeg.org/download.html or configure its path in Settings.

## Usage

1. Launch the app with `python run.py`.
2. Choose an input mode:
   - `Auto`: accepts YouTube URLs or searches YouTube for plain text.
   - `YouTube URL`: accepts only YouTube video or playlist URLs.
   - `Search on YouTube`: treats input as a song-name search.
   - `From .txt`: reads one YouTube URL or song name per non-empty line from a text file.
3. Select output directory, quality, and format.
4. Click `Add to Queue`.

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

```bash
pip install pyinstaller
pyinstaller Muzic.spec
```

Or manually:

```bash
pyinstaller --name="Muzic" --windowed --onefile \
            --add-data="src:src" \
            --add-data="resources:resources" \
            --hidden-import=PySide6 \
            run.py
```

## Disclaimer

This application is for educational purposes only. Users are responsible for ensuring they have the legal right to download any content. Downloading copyrighted material without permission may violate copyright laws and terms of service.

## License

This project is provided as-is for educational purposes.

**Version**: 2.0.0  
**Author**: Muzic Team
