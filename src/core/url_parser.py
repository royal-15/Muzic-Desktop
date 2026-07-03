"""URL parsing and information extraction."""
import re
from typing import Optional, Dict, Any
from dataclasses import dataclass

from ..utils.validators import is_youtube_url


@dataclass
class URLInfo:
    """Information extracted from a URL."""
    url: str
    source: str  # 'youtube'
    type: str  # 'playlist', 'video', 'channel'
    id: Optional[str] = None
    title: Optional[str] = None


class URLParser:
    """Parse and extract information from YouTube URLs."""
    
    @staticmethod
    def parse(url: str) -> Optional[URLInfo]:
        """
        Parse URL and extract information.
        
        Args:
            url: YouTube URL
        
        Returns:
            URLInfo object or None if parsing fails
        """
        if is_youtube_url(url):
            return URLParser._parse_youtube(url)
        return None
    
    @staticmethod
    def _parse_youtube(url: str) -> Optional[URLInfo]:
        """Parse YouTube URL."""
        # YouTube URL patterns:
        # https://www.youtube.com/watch?v=VIDEO_ID
        # https://youtu.be/VIDEO_ID
        # https://www.youtube.com/playlist?list=PLAYLIST_ID
        # https://www.youtube.com/channel/CHANNEL_ID
        
        # Video patterns
        video_patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]+)',
            r'youtube\.com/embed/([a-zA-Z0-9_-]+)',
        ]
        
        for pattern in video_patterns:
            match = re.search(pattern, url)
            if match:
                return URLInfo(
                    url=url,
                    source='youtube',
                    type='video',
                    id=match.group(1)
                )
        
        # Playlist pattern
        playlist_match = re.search(r'[?&]list=([a-zA-Z0-9_-]+)', url)
        if playlist_match:
            return URLInfo(
                url=url,
                source='youtube',
                type='playlist',
                id=playlist_match.group(1)
            )
        
        # Channel patterns
        channel_patterns = [
            r'youtube\.com/channel/([a-zA-Z0-9_-]+)',
            r'youtube\.com/c/([a-zA-Z0-9_-]+)',
            r'youtube\.com/@([a-zA-Z0-9_-]+)',
        ]
        
        for pattern in channel_patterns:
            match = re.search(pattern, url)
            if match:
                return URLInfo(
                    url=url,
                    source='youtube',
                    type='channel',
                    id=match.group(1)
                )
        
        # If no specific match, treat as generic YouTube URL
        return URLInfo(
            url=url,
            source='youtube',
            type='unknown',
            id=None
        )
    
    @staticmethod
    def is_playlist(url: str) -> bool:
        """Check if URL points to a playlist/album."""
        info = URLParser.parse(url)
        if info:
            return info.type == 'playlist'
        return False
    
    @staticmethod
    def get_display_name(url: str) -> str:
        """Get a human-readable display name for the URL."""
        info = URLParser.parse(url)
        if not info:
            return url[:50] + "..." if len(url) > 50 else url
        
        # Format: "YouTube Video"
        source_name = info.source.capitalize()
        type_name = info.type.capitalize()
        
        return f"{source_name} {type_name}"
