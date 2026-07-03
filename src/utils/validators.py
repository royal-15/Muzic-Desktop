"""Input validation utilities."""
import re
from pathlib import Path
from typing import Tuple
from ..config.constants import YOUTUBE_PATTERNS


def is_valid_url(url: str) -> bool:
    """Check if string is a valid URL."""
    if not url or not isinstance(url, str):
        return False
    
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return bool(url_pattern.match(url))


def is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube URL."""
    if not url:
        return False
    
    for pattern in YOUTUBE_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return True
    return False


def detect_url_type(url: str) -> str:
    """
    Detect the type of URL.
    
    Returns:
        'youtube', 'unknown'
    """
    if is_youtube_url(url):
        return 'youtube'
    return 'unknown'


def is_valid_directory(path: str) -> Tuple[bool, str]:
    """
    Validate if a directory path is valid and accessible.
    
    Returns:
        (is_valid, error_message)
    """
    if not path:
        return (False, "Path cannot be empty")
    
    try:
        dir_path = Path(path)
        
        # Check if it's an absolute path
        if not dir_path.is_absolute():
            return (False, "Path must be absolute")
        
        # Try to create the directory if it doesn't exist
        dir_path.mkdir(parents=True, exist_ok=True)
        
        # Check if we have write permissions
        test_file = dir_path / ".muzic_test"
        try:
            test_file.touch()
            test_file.unlink()
        except (OSError, PermissionError):
            return (False, "No write permission for this directory")
        
        return (True, "")
    
    except Exception as e:
        return (False, f"Invalid path: {str(e)}")


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters.
    
    Args:
        filename: Original filename
    
    Returns:
        Sanitized filename safe for filesystem
    """
    # Remove invalid characters for Windows/Unix filesystems
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '', filename)
    
    # Replace multiple spaces with single space
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    # Trim spaces and dots from ends
    sanitized = sanitized.strip(' .')
    
    # Ensure it's not empty
    if not sanitized:
        sanitized = "untitled"
    
    # Limit length (Windows has 255 char limit for filenames)
    max_length = 200  # Leave room for extension
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].strip()
    
    return sanitized


def validate_quality(quality: str) -> bool:
    """Validate quality setting."""
    valid_qualities = ["Best", "320kbps", "256kbps", "192kbps", "128kbps"]
    return quality in valid_qualities


def validate_format(format_str: str) -> bool:
    """Validate audio format."""
    valid_formats = ["mp3", "m4a", "flac", "wav"]
    return format_str.lower() in valid_formats


def parse_multiple_urls(text: str) -> list[str]:
    """
    Parse multiple URLs from text (separated by newlines, commas, or spaces).
    
    Args:
        text: Text containing one or more URLs
    
    Returns:
        List of unique valid URLs
    """
    # Split by common separators
    separators = ['\n', ',', ';', ' ']
    urls = [text]
    
    for sep in separators:
        urls = [url.strip() for chunk in urls for url in chunk.split(sep)]
    
    # Filter valid URLs and remove duplicates while preserving order
    seen = set()
    valid_urls = []
    
    for url in urls:
        url = url.strip()
        if url and url not in seen and is_youtube_url(url):
            seen.add(url)
            valid_urls.append(url)
    
    return valid_urls
