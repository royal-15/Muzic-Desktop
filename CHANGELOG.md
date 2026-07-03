# Changelog

## Version 2.0.0 - Muzic YouTube-Only Downloads

### Changed

- Renamed the project and app to Muzic-Desktop.
- Removed legacy music-service actions and the extra external downloader dependency.
- Simplified downloads to use `yt-dlp` with FFmpeg for YouTube videos, playlists, and searches.
- Updated Settings to configure only max parallel downloads, `yt-dlp`, and FFmpeg paths.

### Added

- Added `From .txt` input mode for batch downloads.
- Each non-empty line in a selected `.txt` file is treated as a YouTube URL or YouTube search.
- Batch downloads use the existing queue and max parallel download limit.

### Removed

- Removed legacy URL/search modes.
- Removed API credential prompts and `.env` credential handling.
- Removed extra downloader command construction, progress parsing, and error handling.
