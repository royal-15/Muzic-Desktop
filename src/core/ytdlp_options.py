"""Shared yt-dlp authentication and JavaScript runtime options."""
import os
import plistlib
import re
import shutil
import subprocess
import sys


SUPPORTED_BROWSERS = (
    "brave", "chrome", "chromium", "edge", "firefox", "opera", "safari",
    "vivaldi", "whale",
)
MINIMUM_DENO_VERSION = (2, 3, 0)


def _browser_from_identifier(identifier: str) -> str:
    """Map OS browser identifiers to yt-dlp's browser names."""
    value = (identifier or "").lower()
    if any(term in value for term in ("brave",)):
        return "brave"
    if any(term in value for term in ("firefox", "mozilla")):
        return "firefox"
    if any(term in value for term in ("edge", "microsoft")):
        return "edge"
    if any(term in value for term in ("vivaldi",)):
        return "vivaldi"
    if any(term in value for term in ("opera",)):
        return "opera"
    if any(term in value for term in ("whale",)):
        return "whale"
    if "safari" in value or "com.apple" in value:
        return "safari"
    if "chromium" in value:
        return "chromium"
    if any(term in value for term in ("chrome", "google")):
        return "chrome"
    return ""


def _run_default_browser_query(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def detect_default_browser() -> str:
    """Detect the system's HTTPS browser without probing other browser profiles."""
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
            ) as key:
                prog_id, _ = winreg.QueryValueEx(key, "ProgId")
            return _browser_from_identifier(prog_id)
        except (OSError, ImportError):
            return ""

    if sys.platform == "darwin":
        exported = _run_default_browser_query([
            "defaults", "export",
            "com.apple.LaunchServices/com.apple.launchservices.secure", "-",
        ])
        if exported:
            try:
                handlers = plistlib.loads(exported.encode("utf-8")).get("LSHandlers", [])
                for handler in handlers:
                    if handler.get("LSHandlerURLScheme", "").lower() == "https":
                        return _browser_from_identifier(handler.get("LSHandlerRoleAll", ""))
            except (plistlib.InvalidFileException, AttributeError, TypeError):
                pass
        return ""

    desktop_id = _run_default_browser_query([
        "xdg-settings", "get", "default-web-browser",
    ])
    if not desktop_id:
        mime_result = _run_default_browser_query([
            "xdg-mime", "query", "default", "x-scheme-handler/https",
        ])
        desktop_id = mime_result
    return _browser_from_identifier(desktop_id)


def authentication_options(settings) -> dict:
    """Build yt-dlp cookie options from non-secret application settings."""
    mode = getattr(settings, "youtube_auth_mode", "none")
    if mode == "browser":
        browser = detect_default_browser()
        if browser in SUPPORTED_BROWSERS:
            return {"cookiesfrombrowser": (browser,)}
        raise ValueError(
            "Muzic could not identify a supported default browser. Set a supported browser "
            "as the system default, or choose a cookies file in Settings."
        )
    elif mode == "file":
        cookie_file = os.path.expanduser(
            str(getattr(settings, "youtube_cookies_file", "") or "").strip()
        )
        if cookie_file:
            if not os.path.isfile(cookie_file):
                raise ValueError("The configured YouTube cookies file could not be found.")
            return {"cookiefile": cookie_file}
    return {}


def javascript_runtime_options(settings, executable: str | None = None) -> dict:
    """Configure optional Deno support without blocking extraction if unavailable."""
    if not getattr(settings, "use_deno_runtime", False):
        return {"js_runtimes": {}}

    if executable is None:
        executable, _, error = deno_runtime_status(settings)
        if error:
            return {"js_runtimes": {}}
    return {"js_runtimes": {"deno": {"path": executable} if executable else {}}}


def deno_executable(settings) -> str:
    """Return a supported Deno executable, or an empty string if unavailable."""
    executable, _, error = deno_runtime_status(settings)
    return "" if error else executable


def deno_runtime_status(settings, deno_path: str | None = None) -> tuple[str, str, str]:
    """Return (executable, version, error) for the configured or discovered Deno."""
    configured_value = getattr(settings, "deno_path", "") if deno_path is None else deno_path
    configured = os.path.expanduser(str(configured_value or "").strip())
    if configured:
        candidate = shutil.which(configured)
        if not candidate and os.path.isfile(configured):
            if os.name == "nt" or os.access(configured, os.X_OK):
                candidate = os.path.realpath(configured)
        if not candidate:
            return "", "", "The configured Deno executable could not be found or run."
    else:
        candidate = shutil.which("deno") or shutil.which("deno.exe")
        if not candidate:
            return "", "", "Deno was not found on PATH."

    try:
        result = subprocess.run(
            [candidate, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return candidate, "", "The configured Deno executable could not be run."

    version_text = "\n".join((result.stdout, result.stderr)).strip()
    match = re.search(r"(?im)^deno\s+(\d+)\.(\d+)\.(\d+)", version_text)
    if result.returncode != 0 or not match:
        return candidate, "", "Deno did not return a recognizable version."
    version_parts = tuple(int(part) for part in match.groups())
    version = ".".join(str(part) for part in version_parts)
    if version_parts < MINIMUM_DENO_VERSION:
        return candidate, version, (
            f"Deno {version} is too old; version 2.3.0 or newer is required."
        )
    return candidate, version, ""


_SECRET_LINE = re.compile(
    r"(?im)^.*?\b(cookie|set-cookie|authorization|proxy-authorization)\s*[:=].*$"
)


def redact_sensitive_text(value: str) -> str:
    """Remove any full credential header from diagnostics before logging/display."""
    return _SECRET_LINE.sub(r"[redacted credential diagnostic]", str(value or ""))
