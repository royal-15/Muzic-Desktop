"""Main application window."""
import shutil
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QComboBox, QLabel,
    QTableWidget, QTableWidgetItem, QProgressBar,
    QFileDialog, QHeaderView, QMessageBox, QSpinBox, QCheckBox,
    QDialog, QFormLayout, QDialogButtonBox, QInputDialog,
    QListWidget, QListWidgetItem, QToolButton, QMenu, QSystemTrayIcon,
    QSizePolicy, QGroupBox, QTabWidget, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QIcon, QCloseEvent, QFontMetrics
from PySide6.QtGui import QDesktopServices

from ..config.settings import SettingsManager
from ..config.constants import (
    APP_NAME, APP_VERSION, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
    WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT,
    QUALITY_OPTIONS, FORMAT_OPTIONS,
    STATUS_QUEUED, STATUS_DOWNLOADING, STATUS_COMPLETED, STATUS_FAILED,
    STATUS_CANCELLED, LOGO_PATH,
)
from ..core.download_manager import DownloadManager
from ..core.download_worker import DownloadTask
from ..core.playlist_resolver import PlaylistResolver
from ..core.ytdlp_options import detect_default_browser, deno_runtime_status
from ..core.url_parser import URLParser
from ..utils.validators import parse_multiple_urls, is_valid_directory, is_valid_url, is_youtube_url, normalize_youtube_url
from ..utils.logger import logger
from .styles.theme import Theme


class _ElidingLabel(QLabel):
    """Single-line label that keeps its full message available as a tooltip."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def set_message(self, message: str) -> None:
        self._full_text = message
        self.setToolTip(message)
        self.setAccessibleDescription(message)
        self._update_elided_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_elided_text()

    def _update_elided_text(self) -> None:
        metrics = QFontMetrics(self.font())
        available_width = max(0, self.contentsRect().width())
        QLabel.setText(
            self,
            metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, available_width),
        )


def _desktop_entry_escape(value: str) -> str:
    """Quote one value for the Exec and Icon fields in a desktop file."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    for character in ("$", "`"):
        escaped = escaped.replace(character, "\\" + character)
    escaped = escaped.replace("%", "%%")
    return f'"{escaped}"'


def _powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _remove_versioned_muzic_entries(directory: Path, suffix: str) -> None:
    """Remove old version-named Muzic launchers from a user menu directory."""
    versioned_name = re.compile(
        rf"^muzic(?:[ _-]+v?)\d+(?:\.\d+){{1,3}}{re.escape(suffix)}$",
        re.IGNORECASE,
    )
    for entry in directory.iterdir():
        if not entry.is_file() or not versioned_name.fullmatch(entry.name):
            continue

        # A Linux desktop file must also identify itself as a Muzic application;
        # this avoids deleting an unrelated file that happens to share the name.
        if suffix == ".desktop":
            try:
                contents = entry.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if not re.search(r"(?im)^Name=Muzic(?:\s+v?\d+(?:\.\d+){1,3})?\s*$", contents):
                continue

        entry.unlink()


def _create_desktop_entry_for_current_user() -> None:
    """Create a current-user launcher entry for the current platform."""
    if sys.platform == "win32":
        _create_windows_start_menu_entry()
    elif sys.platform.startswith("linux"):
        _create_linux_applications_entry()
    else:
        raise OSError("Launcher entries are supported on Windows and Linux.")


def _launch_target() -> tuple[str, str]:
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    launcher = sys.executable
    if sys.platform == "win32":
        pythonw = Path(launcher).with_name("pythonw.exe")
        if pythonw.is_file():
            launcher = str(pythonw)
    return launcher, str(Path(__file__).resolve().parents[2] / "run.py")


def _create_windows_start_menu_entry() -> None:
    programs = Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    programs.mkdir(parents=True, exist_ok=True)
    shortcut = programs / "Muzic.lnk"
    target, arguments = _launch_target()
    icon_path = sys.executable if getattr(sys, "frozen", False) else str(LOGO_PATH)
    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$shortcut = $shell.CreateShortcut({_powershell_literal(str(shortcut))}); "
        f"$shortcut.TargetPath = {_powershell_literal(target)}; "
        f"$shortcut.Arguments = {_powershell_literal(arguments)}; "
        f"$shortcut.WorkingDirectory = {_powershell_literal(str(Path(target).parent))}; "
        f"$shortcut.IconLocation = {_powershell_literal(icon_path)}; "
        "$shortcut.Save()"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
    )
    _remove_versioned_muzic_entries(programs, ".lnk")


def _create_linux_applications_entry() -> None:
    applications = Path.home() / ".local" / "share" / "applications"
    icons = Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    applications.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)
    if not LOGO_PATH.is_file():
        raise OSError(f"Application icon not found: {LOGO_PATH}")

    icon_path = icons / "muzic.png"
    pixmap = QIcon(str(LOGO_PATH)).pixmap(256, 256)
    if pixmap.isNull() or not pixmap.save(str(icon_path), "PNG"):
        raise OSError("Could not prepare the application menu icon.")

    target, arguments = _launch_target()
    exec_value = " ".join(_desktop_entry_escape(part) for part in (target, arguments) if part)
    entry = applications / "muzic.desktop"
    entry.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Muzic\n"
        "Comment=Modern Music Downloader\n"
        f"Exec={exec_value}\n"
        f"Icon={icon_path}\n"
        "Terminal=false\n"
        "Categories=AudioVideo;Audio;\n",
        encoding="utf-8",
    )
    entry.chmod(0o755)
    _remove_versioned_muzic_entries(applications, ".desktop")


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        # Load settings
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.settings

        if LOGO_PATH.is_file():
            app_icon = QIcon(str(LOGO_PATH))
            self.setWindowIcon(app_icon)
            app = QApplication.instance()
            if app:
                app.setWindowIcon(app_icon)

        self.tray_icon = QSystemTrayIcon(self)
        if LOGO_PATH.is_file():
            self.tray_icon.setIcon(QIcon(str(LOGO_PATH)))
        self.tray_icon.setToolTip(APP_NAME)
        self.tray_icon.show()
        
        # Initialize theme
        self.theme = Theme("dark")
        
        # Initialize download manager
        self.download_manager = DownloadManager(self.settings, self)
        self._playlist_resolver: PlaylistResolver | None = None
        self._closing = False
        self._playlist_resolution_active = False
        self._status_message_generation = 0
        
        # Setup UI
        self._setup_window()
        self._setup_ui()
        self._apply_theme()
        self._connect_signals()
        
        # Show disclaimer if first run
        if self.settings.first_run:
            self._show_disclaimer()
            if not self.settings.first_run and (
                sys.platform == "win32" or sys.platform.startswith("linux")
            ):
                self._prompt_add_desktop_entry()

        # Do not prompt for FFmpeg if the first-run disclaimer was declined.
        if not self.settings.first_run:
            self._ensure_ffmpeg_path()

        logger.info(f"{APP_NAME} v{APP_VERSION} started")

    def _ensure_ffmpeg_path(self) -> None:
        """Prompt for FFmpeg when the configured executable cannot be found."""
        configured_path = (self.settings.ffmpeg_path or "ffmpeg.exe").strip()
        if self._resolve_ffmpeg_path(configured_path):
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select FFmpeg Executable",
            str(Path.home()),
            "FFmpeg executable (ffmpeg.exe);;Executable files (*.exe);;All files (*)",
        )
        if file_path:
            self.settings.ffmpeg_path = file_path
            self.settings_manager.save()

    @staticmethod
    def _resolve_ffmpeg_path(configured_path: str) -> str | None:
        """Return the executable path if it exists directly or on PATH."""
        candidate = Path(configured_path).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        return shutil.which(configured_path) or (
            shutil.which("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
            if Path(configured_path).name.lower() in {"ffmpeg.exe", "ffmpeg"}
            else None
        )
    
    def _setup_window(self) -> None:
        """Configure main window properties."""
        self.setWindowTitle(f"{APP_NAME} - Modern Music Downloader")
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        
        # Restore window size
        if self.settings.window_maximized:
            self.showMaximized()
        else:
            self.resize(self.settings.window_width, self.settings.window_height)
    
    def _setup_ui(self) -> None:
        """Setup user interface."""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(16, 16, 16, 16)
        
        # Title
        title_label = QLabel(f"🎵 {APP_NAME}")
        title_label.setObjectName("subtitle")
        main_layout.addWidget(title_label)
        
        # Download panel
        download_panel = QGroupBox("Download")
        download_panel_layout = QVBoxLayout(download_panel)
        download_panel_layout.setSpacing(8)
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        
        # URL/Search input
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste URL or enter song name...")
        self.url_input.setAccessibleName("URL or song search")
        self.url_input.setToolTip("Paste a YouTube URL or enter a song name")
        self.url_input.returnPressed.connect(self._on_add_clicked)
        input_layout.addWidget(self.url_input, 3)

        self.input_file_button = QPushButton("Browse .txt")
        self.input_file_button.setObjectName("secondaryButton")
        self.input_file_button.clicked.connect(self._on_browse_input_file_clicked)
        self.input_file_button.setVisible(False)
        self.input_file_button.setToolTip("Choose a text file with one URL or song name per line")
        input_layout.addWidget(self.input_file_button)
        
        # Query type selector
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "Auto",
            "YouTube URL",
            "Search on YouTube",
            "From .txt",
        ])
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.mode_combo.setAccessibleName("Input mode")
        input_layout.addWidget(self.mode_combo, 1)
        download_panel_layout.addLayout(input_layout)

        options_layout = QHBoxLayout()
        options_layout.setSpacing(8)
        
        # Quality selector
        quality_label = QLabel("Quality:")
        options_layout.addWidget(quality_label)
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(QUALITY_OPTIONS)
        self.quality_combo.setCurrentText(self.settings.default_quality)
        self.quality_combo.currentTextChanged.connect(self._on_quality_changed)
        options_layout.addWidget(self.quality_combo)
        
        # Format selector
        format_label = QLabel("Format:")
        options_layout.addWidget(format_label)
        
        self.format_combo = QComboBox()
        self.format_combo.addItems(FORMAT_OPTIONS)
        self.format_combo.setCurrentText(self.settings.default_format)
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        options_layout.addWidget(self.format_combo)
        
        # Add button
        self.add_button = QPushButton("Add to Queue")
        self.add_button.clicked.connect(self._on_add_clicked)
        self.add_button.setToolTip("Add downloads to the queue; available downloads start automatically")
        self.add_button.setDefault(True)
        options_layout.addStretch()
        options_layout.addWidget(self.add_button)
        download_panel_layout.addLayout(options_layout)

        main_layout.addWidget(download_panel)
        
        # Queue table
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(7)
        self.queue_table.setHorizontalHeaderLabels([
            "ID", "Name", "URL", "Status", "Progress", "Speed", "Dest"
        ])
        queue_header = self.queue_table.horizontalHeader()
        queue_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        queue_header.setStretchLastSection(False)
        self.queue_table.cellClicked.connect(self._on_queue_cell_clicked)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.queue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.queue_table.setAlternatingRowColors(True)
        self.queue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_table.customContextMenuRequested.connect(self._show_queue_context_menu)
        main_layout.addWidget(self.queue_table, 1)
        QTimer.singleShot(0, self._set_default_queue_column_widths)
        
        # Bottom controls (two rows: output, playlists + queue actions)
        bottom_container = QVBoxLayout()
        bottom_container.setSpacing(4)

        # Row 1: Output directory
        output_layout = QHBoxLayout()
        output_layout.setSpacing(8)

        dir_label = QLabel("Output:")
        output_layout.addWidget(dir_label)

        self.output_dir_input = QLineEdit()
        self.output_dir_input.setText(self.settings.output_dir)
        self.output_dir_input.setAccessibleName("Download destination")
        output_layout.addWidget(self.output_dir_input, 2)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.setObjectName("secondaryButton")
        self.browse_button.clicked.connect(self._on_browse_clicked)
        output_layout.addWidget(self.browse_button)

        bottom_container.addLayout(output_layout)

        # Row 2: Playlist controls on the left, actions on the right
        bottom_row_layout = QHBoxLayout()
        bottom_row_layout.setSpacing(8)

        # Left section: playlist controls
        playlist_label = QLabel("Playlists:")
        bottom_row_layout.addWidget(playlist_label)

        # Saved playlist folders
        self.playlist_combo = QComboBox()
        self._refresh_playlist_folders()
        self.playlist_combo.currentIndexChanged.connect(self._on_playlist_selected)
        bottom_row_layout.addWidget(self.playlist_combo)

        self.playlists_button = QToolButton()
        self.playlists_button.setText("Playlists…")
        self.playlists_button.setObjectName("secondaryButton")
        playlist_menu = QMenu(self.playlists_button)
        playlist_menu.addAction("Save Current Playlist…", self._on_save_playlist_folder_clicked)
        playlist_menu.addAction("Manage Playlists…", self._on_manage_playlist_folders_clicked)
        self.playlists_button.setMenu(playlist_menu)
        self.playlists_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.playlists_button.setToolTip("Save or manage playlist folder mappings")
        bottom_row_layout.addWidget(self.playlists_button)

        bottom_row_layout.addStretch()

        # Right section: queue controls
        self.cancel_all_button = QPushButton("Cancel All")
        self.cancel_all_button.setObjectName("secondaryButton")
        self.cancel_all_button.clicked.connect(self._on_cancel_all_clicked)
        bottom_row_layout.addWidget(self.cancel_all_button)

        # Clear menu (Completed / Failed / All)
        self.clear_menu_button = QToolButton()
        self.clear_menu_button.setText("Clear ▾")
        self.clear_menu_button.setObjectName("secondaryButton")
        clear_menu = QMenu(self.clear_menu_button)

        clear_completed_action = clear_menu.addAction("Clear Completed")
        clear_completed_action.triggered.connect(self._on_clear_completed_clicked)

        clear_failed_action = clear_menu.addAction("Clear Failed")
        clear_failed_action.triggered.connect(self._on_clear_failed_clicked)

        clear_menu.addSeparator()

        clear_all_action = clear_menu.addAction("Clear All")
        clear_all_action.triggered.connect(self._on_clear_all_clicked)

        self.clear_menu_button.setMenu(clear_menu)
        self.clear_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        bottom_row_layout.addWidget(self.clear_menu_button)

        self.settings_button = QPushButton("⚙ Settings")
        self.settings_button.setObjectName("secondaryButton")
        self.settings_button.clicked.connect(self._on_settings_clicked)
        bottom_row_layout.addWidget(self.settings_button)

        bottom_container.addLayout(bottom_row_layout)

        main_layout.addLayout(bottom_container)
        
        # Keep messages flexible on the left and queue counts anchored on the right.
        status_bar = self.statusBar()
        status_bar.setSizeGripEnabled(False)
        self.status_message_label = _ElidingLabel(self)
        self.status_message_label.setObjectName("statusMessage")
        self.status_message_label.set_message("Ready")
        status_bar.addWidget(self.status_message_label, 1)

        self.queue_status_widget = QWidget(self)
        self.queue_status_widget.setObjectName("queueStatusCounts")
        counts_layout = QHBoxLayout(self.queue_status_widget)
        counts_layout.setContentsMargins(8, 0, 8, 0)
        counts_layout.setSpacing(10)
        self._queue_count_labels = {}
        for key, label in (
            ("queued", "Pending"),
            ("downloading", "Downloading"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ):
            count_label = QLabel(f"{label} 0", self.queue_status_widget)
            count_label.setObjectName("queueCountFailed" if key == "failed" else "queueCount")
            count_label.setToolTip(f"{label} downloads")
            count_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            self._queue_count_labels[key] = (label, count_label)
            counts_layout.addWidget(count_label)
        self.queue_status_widget.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        status_bar.addPermanentWidget(self.queue_status_widget)
        self._update_stats()

    def _set_default_queue_column_widths(self) -> None:
        """Size queue columns to fill the initial viewport while keeping them resizable."""
        viewport_width = self.queue_table.viewport().width()
        if viewport_width <= 0:
            return

        proportions = (0.055, 0.22, 0.20, 0.11, 0.12, 0.10, 0.195)
        minimums = (50, 145, 145, 88, 96, 86, 180)
        widths = [
            max(minimum, int(viewport_width * proportion))
            for minimum, proportion in zip(minimums, proportions)
        ]
        if sum(widths) < viewport_width:
            widths[-1] += viewport_width - sum(widths)

        for column, width in enumerate(widths):
            self.queue_table.setColumnWidth(column, width)
    
    def _apply_theme(self) -> None:
        """Apply theme to the application."""
        stylesheet = self.theme.get_stylesheet()
        self.setStyleSheet(stylesheet)
    
    def _connect_signals(self) -> None:
        """Connect download manager signals."""
        self.download_manager.task_added.connect(self._on_task_added)
        self.download_manager.task_updated.connect(self._on_task_updated)
        self.download_manager.task_completed.connect(self._on_task_completed)
        self.download_manager.task_failed.connect(self._on_task_failed)
        self.download_manager.queue_changed.connect(self._update_stats)
        self.download_manager.queue_changed.connect(self._refresh_table)
    
    def _on_add_clicked(self) -> None:
        """Handle add button click."""
        if self._playlist_resolver and self._playlist_resolver.isRunning():
            self._show_feedback("Please wait for playlist resolution to finish", "info", 2500)
            return

        query_text = self.url_input.text().strip()
        mode = self.mode_combo.currentText()
        
        if not query_text:
            if mode == "From .txt":
                self._show_feedback("Please select a .txt file", "warning")
            else:
                self._show_feedback("Please enter a URL or search query", "warning")
            return
        
        # Update settings
        self.settings.output_dir = self.output_dir_input.text().strip() or self.settings.output_dir
        if not self.settings_manager.save():
            self._show_feedback("Settings could not be saved", "error", 3500)
        
        # Process query based on mode
        queries = self._process_query(query_text, mode)
        
        if not queries:
            self._show_feedback("No valid URLs or queries found", "error")
            return
        
        playlist_urls = [query for query in queries if URLParser.is_playlist(query)]
        if playlist_urls:
            self._resolve_playlists(queries, mode == "From .txt")
        else:
            self.download_manager.add_tasks(queries)
            self._show_feedback(f"Added {len(queries)} download(s) to queue", "success")

        # Clear input after the submission has been accepted.
        self.url_input.clear()

    def _resolve_playlists(self, queries: list[str], from_txt: bool) -> None:
        """Expand playlist URLs before adding individual tasks to the queue."""
        self._playlist_resolution_active = True
        self._set_status_message(
            "Resolving playlist URLs from text file…" if from_txt else "Resolving playlist songs…"
        )

        self.add_button.setEnabled(False)
        self._playlist_resolver = PlaylistResolver(
            queries,
            getattr(self.settings, "timeout_seconds", 300),
            output_dir=self.settings.output_dir,
            audio_format=self.settings.default_format or "mp3",
            ffmpeg_path=self.settings.ffmpeg_path,
            settings=self.settings,
            parent=self,
        )
        self._playlist_resolver.resolved.connect(self._on_playlists_resolved)
        self._playlist_resolver.finished.connect(self._on_playlist_resolver_finished)
        self._playlist_resolver.start()

    def _on_playlists_resolved(self, results: list) -> None:
        """Queue resolved tracks and ask before falling back for failures."""
        if self._closing:
            return
        queries_to_queue = []
        completed_items = []
        unresolved_count = 0
        for original, resolution in results:
            if resolution is None:
                queries_to_queue.append(original)
                continue

            if resolution.video_urls:
                titles = resolution.video_titles or []
                for index, video_url in enumerate(resolution.video_urls):
                    title = titles[index] if index < len(titles) else ""
                    existing_file = resolution.existing_files.get(video_url)
                    if existing_file:
                        completed_items.append((video_url, existing_file, title))
                    else:
                        queries_to_queue.append(video_url)
                continue

            unresolved_count += 1
            answer = QMessageBox.question(
                self,
                "Playlist Could Not Be Expanded",
                f"Could not resolve playlist:\n{resolution.playlist_url}\n\n"
                f"{resolution.error}\n\nQueue the playlist using the current download behavior?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                queries_to_queue.append(resolution.playlist_url)

        for video_url, output_file, title in completed_items:
            self.download_manager.add_completed_task(video_url, output_file, title)

        if queries_to_queue:
            self.download_manager.add_tasks(queries_to_queue)
        self._playlist_resolution_active = False
        result_parts = [f"{len(queries_to_queue)} queued", f"{len(completed_items)} already complete"]
        if unresolved_count:
            result_parts.append(f"{unresolved_count} unresolved")
        self._set_status_message("Playlist resolution finished · " + " · ".join(result_parts))

    def _on_playlist_resolver_finished(self) -> None:
        self.add_button.setEnabled(True)
        self._playlist_resolver = None
        if self._playlist_resolution_active:
            self._playlist_resolution_active = False
            self._set_status_message("Playlist resolution finished")
    
    def _process_query(self, text: str, mode: str) -> list[str]:
        """Process input text based on selected mode."""
        if mode == "From .txt":
            return self._process_txt_file(text)

        # Try to parse as multiple URLs first
        urls = parse_multiple_urls(text)
        
        if urls and mode == "Auto":
            # Multiple URLs detected, use them as-is
            return urls
        elif urls and len(urls) == 1:
            # Single URL, process based on mode
            url = urls[0]
            
            if mode == "Auto":
                return [url]
            elif mode == "YouTube URL":
                if is_youtube_url(url):
                    return [url]
                else:
                    return []  # Invalid for this mode
            elif mode == "Search on YouTube":
                return [url] if is_youtube_url(url) else [f"ytsearch1:{self._append_song(text)}"]
        else:
            if is_valid_url(text):
                self._show_feedback("Only YouTube URLs are supported", "error", 3000)
                return []

            # No valid URLs, treat as search query
            if mode == "Auto" or mode == "Search on YouTube":
                # Default to YouTube search
                return [f"ytsearch1:{self._append_song(text)}"]
            elif mode == "YouTube URL":
                # Must be a URL in this mode
                return []
        
        return []

    @staticmethod
    def _append_song(query: str) -> str:
        """Bias YouTube search toward complete songs."""
        query = query.strip()
        return query if re.search(r"\bsong\b", query, re.IGNORECASE) else f"{query} song"

    def _process_txt_file(self, file_path: str) -> list[str]:
        """Read a .txt batch file and convert each line to a download query."""
        path = Path(file_path).expanduser()

        if path.suffix.lower() != ".txt":
            self._show_feedback("Please select a .txt file", "error", 3000)
            return []

        if not path.is_file():
            self._show_feedback("Text file not found", "error", 3000)
            return []

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            self._show_feedback(f"Could not read file: {e}", "error", 4000)
            return []

        queries = []
        seen = set()

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line in seen:
                continue

            youtube_url = normalize_youtube_url(line)
            if youtube_url:
                query = youtube_url
            elif is_valid_url(line):
                continue
            else:
                query = f"ytsearch1:{self._append_song(line)}"

            seen.add(line)
            queries.append(query)

        if not queries:
            self._show_feedback("No YouTube URLs or search names found in file", "error", 4000)

        return queries

    def _extract_youtube_playlist_id(self, url: str) -> str | None:
        """Extract YouTube playlist ID from a URL, ignoring unrelated params.

        Returns the playlist ID from the `list` query parameter, or None.
        """
        if not is_youtube_url(url):
            return None

        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(url)
        values = parse_qs(parsed.query).get("list", [])
        if not values:
            return None
        return values[0].strip() or None

    def _get_saved_playlist_name_for_url(self, url: str) -> str | None:
        """Return saved playlist name that matches the given YouTube playlist URL.

        This uses the `playlist_urls` mapping from settings and matches by playlist ID.
        """
        if not url:
            return None

        if not hasattr(self.settings, "playlist_urls") or not self.settings.playlist_urls:
            return None

        target_id = self._extract_youtube_playlist_id(url)
        if not target_id:
            return None

        for name, saved_url in self.settings.playlist_urls.items():
            saved_id = self._extract_youtube_playlist_id(saved_url or "")
            if saved_id and saved_id.lower() == target_id.lower():
                return name

        return None

    def _get_task_display_and_tooltip(self, task: DownloadTask) -> tuple[str, str]:
        """Return (display_text, tooltip) for the queue URL column.

        - If the task URL matches a saved playlist, show the playlist name as display
          text and use the URL as tooltip.
        - Otherwise, show a truncated URL and use the full URL as tooltip.
        """
        url = task.url or ""
        playlist_name = self._get_saved_playlist_name_for_url(url)

        if playlist_name:
            # Show friendly playlist name, keep URL accessible via tooltip
            return playlist_name, url

        if len(url) > 80:
            return url[:80] + "...", url

        return url, url
    
    def _on_mode_changed(self, mode: str) -> None:
        """Handle mode selector change."""
        # Update placeholder text based on mode
        placeholders = {
            "Auto": "Paste URL or enter song name...",
            "YouTube URL": "Paste YouTube URL...",
            "Search on YouTube": "Search for songs on YouTube...",
            "From .txt": "Select a .txt file with one YouTube URL or song name per line...",
        }
        self.url_input.setPlaceholderText(placeholders.get(mode, "Paste URL or enter song name..."))
        self.input_file_button.setVisible(mode == "From .txt")

    def _on_browse_input_file_clicked(self) -> None:
        """Select a .txt file for batch input."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Text File",
            str(Path.home()),
            "Text files (*.txt)",
        )

        if file_path:
            self.url_input.setText(file_path)
    
    def _on_quality_changed(self, quality: str) -> None:
        """Handle quality change."""
        self.settings.default_quality = quality
        self.settings_manager.save()
    
    def _on_format_changed(self, format_str: str) -> None:
        """Handle format change."""
        self.settings.default_format = format_str
        self.settings_manager.save()
    
    def _on_browse_clicked(self) -> None:
        """Handle browse button click."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            self.output_dir_input.text()
        )
        
        if directory:
            self.output_dir_input.setText(directory)
            self.settings.output_dir = directory
            self.settings_manager.save()

    def _refresh_playlist_folders(self) -> None:
        """Populate saved playlist folders combo box."""
        # This may be called before the combo is created during initialization
        if not hasattr(self, "playlist_combo"):
            return

        self.playlist_combo.blockSignals(True)
        self.playlist_combo.clear()
        self.playlist_combo.addItem("Saved playlists...")

        playlist_folders = getattr(self.settings, "playlist_folders", {}) or {}
        for name in sorted(playlist_folders.keys()):
            self.playlist_combo.addItem(name)

        self.playlist_combo.blockSignals(False)

    def _on_playlist_selected(self, index: int) -> None:
        """Apply selected saved playlist folder and URL to the interface."""
        if index <= 0:
            # Placeholder item selected
            return

        name = self.playlist_combo.currentText()
        folder = self.settings.playlist_folders.get(name) if hasattr(self.settings, "playlist_folders") else None
        if not folder:
            return

        # Set the output directory
        self.output_dir_input.setText(folder)
        self.settings.output_dir = folder
        self.settings_manager.save()
        
        # Also populate the URL input if available
        url = self.settings.playlist_urls.get(name) if hasattr(self.settings, "playlist_urls") else None
        if url:
            self.url_input.setText(url)
            self._show_feedback(f"Loaded playlist '{name}' - Click 'Add to Queue' to download", "info", 3000)
        else:
            self._show_feedback(f"Output folder set for '{name}'", "info", 2000)

    def _on_save_playlist_folder_clicked(self) -> None:
        """Save the current output directory under a playlist name."""
        directory = self.output_dir_input.text().strip()
        if not directory:
            self._show_feedback("Please select an output directory first", "warning", 3000)
            return

        is_valid, error_message = is_valid_directory(directory)
        if not is_valid:
            self._show_feedback(error_message, "error", 3000)
            return

        name, ok = QInputDialog.getText(
            self,
            "Save Playlist Folder",
            "Playlist name:",
        )
        if not ok:
            return

        name = name.strip()
        if not name:
            self._show_feedback("Playlist name cannot be empty", "warning", 3000)
            return

        if not hasattr(self.settings, "playlist_folders") or self.settings.playlist_folders is None:
            self.settings.playlist_folders = {}

        # Optional playlist URL (prefill from current URL input if available)
        default_url = self.url_input.text().strip()
        url, ok_url = QInputDialog.getText(
            self,
            "Playlist URL (optional)",
            "Playlist URL:",
            text=default_url,
        )
        if not ok_url:
            url = ""

        self.settings.playlist_folders[name] = directory

        if not hasattr(self.settings, "playlist_urls") or self.settings.playlist_urls is None:
            self.settings.playlist_urls = {}
        url = url.strip()
        if url:
            self.settings.playlist_urls[name] = url

        self.settings_manager.save()
        self._refresh_playlist_folders()

        # Select the newly added playlist in the combo box
        index = self.playlist_combo.findText(name)
        if index != -1:
            self.playlist_combo.setCurrentIndex(index)

        self._show_feedback(f"Saved folder for playlist '{name}'", "success", 3000)

    def _on_manage_playlist_folders_clicked(self) -> None:
        """Open dialog to manage saved playlist-folder mappings."""
        playlist_folders = getattr(self.settings, "playlist_folders", {}) or {}
        playlist_urls = getattr(self.settings, "playlist_urls", {}) or {}
        dialog = ManagePlaylistsDialog(playlist_folders, playlist_urls, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Update settings with modified mappings
            self.settings.playlist_folders = dialog.get_playlist_folders()
            self.settings.playlist_urls = dialog.get_playlist_urls()
            self.settings_manager.save()
            self._refresh_playlist_folders()
            self._show_feedback("Updated saved playlists", "success", 2000)
        
    def _on_start_all_clicked(self) -> None:
        """Handle start all button click."""
        self.download_manager.start_all_queued()
    
    def _on_cancel_all_clicked(self) -> None:
        """Handle cancel all button click."""
        self.download_manager.cancel_all()
        self._show_feedback("Cancelled all downloads", "info")
    
    def _on_clear_completed_clicked(self) -> None:
        """Handle clear completed button click."""
        self.download_manager.clear_completed()
        self._show_feedback("Cleared completed downloads", "info", 2000)
    
    def _on_clear_failed_clicked(self) -> None:
        """Handle clear failed button click."""
        self.download_manager.clear_failed()
        self._show_feedback("Cleared failed downloads", "info", 2000)
    
    def _on_clear_all_clicked(self) -> None:
        """Handle clear all button click."""
        reply = QMessageBox.question(
            self,
            "Clear All",
            "Are you sure you want to clear all downloads from the queue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.download_manager.clear_all()
            self._show_feedback("Cleared all downloads", "info", 2000)
    
    def _on_settings_clicked(self) -> None:
        """Handle settings button click."""
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if not self.settings_manager.save():
                self._show_feedback("Settings could not be saved. Check the configured values and config folder permissions.", "error", 4500)
                return
            self.output_dir_input.setText(self.settings.output_dir)
            self._show_feedback("Settings saved", "success")
    
    def _on_task_added(self, task: DownloadTask) -> None:
        """Handle new task added."""
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)
        
        self._populate_task_row(row, task)
    
    def _on_task_updated(self, task: DownloadTask) -> None:
        """Handle task update."""
        # Find task row
        for row in range(self.queue_table.rowCount()):
            id_item = self.queue_table.item(row, 0)
            if id_item and int(id_item.text()) == task.id:
                title_item = self.queue_table.item(row, 1)
                if title_item and task.title:
                    title_item.setText(task.title)
                    title_item.setToolTip(task.title)

                status_item = self.queue_table.item(row, 3)
                if status_item:
                    status_item.setText(task.status_message or task.status.capitalize())
                    status_item.setToolTip(task.error_message or task.status_message or "")
                
                # Update progress bar
                progress_bar = self.queue_table.cellWidget(row, 4)
                if isinstance(progress_bar, QProgressBar):
                    progress_bar.setValue(task.progress)
                
                speed_item = self.queue_table.item(row, 5)
                if speed_item:
                    speed_item.setText(task.speed or "")

                destination_item = self.queue_table.item(row, 6)
                if destination_item:
                    destination_item.setText(task.output_dir)
                    destination_item.setToolTip(task.output_dir)
                
                break
    
    def _on_task_completed(self, task: DownloadTask) -> None:
        """Handle task completion."""
        logger.info(f"Task {task.id} completed")
        if task.error_message == "Already present and validated":
            return
        title = task.title or "Download completed"
        self._show_system_notification("Download complete", title)
    
    def _on_task_failed(self, task: DownloadTask) -> None:
        """Handle task failure."""
        logger.error(f"Task {task.id} failed: {task.error_message}")
        title = task.title or f"Download {task.id}"
        reason = (task.error_message or "Check the queue for details").strip()
        self._show_system_notification("Download failed", f"{title}: {reason[:140]}", failed=True)

    def _show_system_notification(self, title: str, message: str, failed: bool = False) -> None:
        if self.tray_icon.isSystemTrayAvailable() and self.tray_icon.supportsMessages():
            icon = (
                QSystemTrayIcon.MessageIcon.Critical
                if failed else QSystemTrayIcon.MessageIcon.Information
            )
            self.tray_icon.showMessage(
                title, message, icon, 5000
            )
        else:
            self._show_feedback(f"{title}: {message}", duration=8000)

    def _show_feedback(self, message: str, toast_type: str = "info", duration: int = 3000) -> None:
        """Show brief feedback without interrupting an active playlist resolution."""
        del toast_type  # Retained at call sites for message category compatibility.
        if self._playlist_resolution_active:
            return
        self._set_status_message(message, duration)

    def _set_status_message(self, message: str, duration: int = 0) -> None:
        self._status_message_generation += 1
        generation = self._status_message_generation
        self.status_message_label.set_message(message)
        if duration > 0:
            QTimer.singleShot(duration, lambda: self._clear_status_message(generation))

    def _clear_status_message(self, generation: int) -> None:
        if generation == self._status_message_generation and not self._playlist_resolution_active:
            self._set_status_message("Ready")

    def _show_queue_context_menu(self, position) -> None:
        index = self.queue_table.indexAt(position)
        if not index.isValid():
            return

        row = index.row()
        id_item = self.queue_table.item(row, 0)
        if not id_item:
            return
        task = self.download_manager.get_task(int(id_item.text()))
        if not task:
            return

        menu = QMenu(self)
        if index.column() == 1:
            menu.addAction("Copy name", lambda: self._copy_to_clipboard(task.title or ""))
        elif index.column() == 2:
            menu.addAction("Copy URL", lambda: self._copy_to_clipboard(task.url or ""))

        if task.status == STATUS_FAILED:
            menu.addSeparator()
            menu.addAction("Retry", lambda task_id=task.id: self._retry_task(task_id))
        elif task.status in (STATUS_QUEUED, STATUS_DOWNLOADING):
            menu.addSeparator()
            menu.addAction("Cancel download", lambda task_id=task.id: self.download_manager.cancel_task(task_id))

        if task.output_dir:
            menu.addSeparator()
            menu.addAction("Open destination", lambda path=task.output_dir: self._open_destination(path))

        menu.exec(self.queue_table.viewport().mapToGlobal(position))

    def _copy_to_clipboard(self, value: str) -> None:
        QApplication.clipboard().setText(value)
        self._show_feedback("Copied to clipboard")

    def _retry_task(self, task_id: int) -> None:
        if self.download_manager.retry_task(task_id):
            self._show_feedback(f"Retrying download {task_id}")
    
    def _refresh_table(self) -> None:
        """Rebuild the queue table from current tasks."""
        # Clear the table
        self.queue_table.setRowCount(0)
        
        # Rebuild from download manager tasks
        all_tasks = self.download_manager.get_all_tasks()
        for task in all_tasks:
            row = self.queue_table.rowCount()
            self.queue_table.insertRow(row)
            self._populate_task_row(row, task)

    def _populate_task_row(self, row: int, task: DownloadTask) -> None:
        self.queue_table.setItem(row, 0, QTableWidgetItem(str(task.id)))

        title = task.title or "Resolving title…"
        title_item = QTableWidgetItem(title)
        title_item.setToolTip(task.title or "Title is read from YouTube metadata")
        self.queue_table.setItem(row, 1, title_item)

        url_item = QTableWidgetItem(task.url)
        url_item.setToolTip(task.url)
        self.queue_table.setItem(row, 2, url_item)
        status_item = QTableWidgetItem(task.status.capitalize())
        status_item.setToolTip(task.error_message or "")
        self.queue_table.setItem(row, 3, status_item)

        progress_bar = QProgressBar()
        progress_bar.setValue(task.progress)
        self.queue_table.setCellWidget(row, 4, progress_bar)
        self.queue_table.setItem(row, 5, QTableWidgetItem(task.speed or ""))

        destination_item = QTableWidgetItem(task.output_dir)
        destination_item.setToolTip(f"Open folder: {task.output_dir}")
        destination_item.setForeground(self.palette().link())
        self.queue_table.setItem(row, 6, destination_item)

    def _on_queue_cell_clicked(self, row: int, column: int) -> None:
        if column != 6:
            return
        id_item = self.queue_table.item(row, 0)
        if not id_item:
            return
        task = self.download_manager.get_task(int(id_item.text()))
        if not task or not task.output_dir:
            return
        self._open_destination(task.output_dir)

    def _open_destination(self, path: str) -> None:
        destination = Path(path).expanduser()
        try:
            destination.mkdir(parents=True, exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(destination.resolve()))):
                self._show_feedback("Could not open destination folder", "error", 3000)
        except OSError as error:
            self._show_feedback(f"Could not open destination folder: {error}", "error", 4000)
    
    def _update_stats(self) -> None:
        """Update the fixed right-side queue summary."""
        stats = self.download_manager.get_stats()
        for key, (label, count_label) in self._queue_count_labels.items():
            count_label.setText(f"{label} {stats[key]}")
            count_label.setAccessibleName(f"{label}: {stats[key]}")
            count_label.setProperty("attention", key == "failed" and stats[key] > 0)
            count_label.style().unpolish(count_label)
            count_label.style().polish(count_label)
    
    def _show_disclaimer(self) -> None:
        """Show disclaimer dialog on first run."""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Disclaimer")
        msg_box.setText(
            "This application is intended only for downloading audio you have the legal "
            "right to download (e.g., your own content or content that is free to download).\n\n"
            "Downloading copyrighted material may violate Terms of Service and/or copyright law "
            "in your jurisdiction.\n\n"
            "By clicking 'I Understand', you acknowledge that you are solely responsible "
            "for how you use this application."
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        msg_box.button(QMessageBox.StandardButton.Ok).setText("I Understand")
        
        result = msg_box.exec()
        
        if result == QMessageBox.StandardButton.Ok:
            self.settings.disclaimer_accepted = True
            self.settings.first_run = False
            self.settings_manager.save()
        else:
            QTimer.singleShot(0, self.close)

    def _prompt_add_desktop_entry(self) -> None:
        """Offer a current-user launcher entry once after disclaimer acceptance."""
        result = QMessageBox.question(
            self,
            "Add Muzic to Applications?",
            "Would you like to add Muzic to your applications menu?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if result == QMessageBox.StandardButton.Yes:
            try:
                _create_desktop_entry_for_current_user()
            except (OSError, subprocess.SubprocessError) as error:
                QMessageBox.critical(self, "Launcher Entry Failed", str(error))
                return
            QMessageBox.information(
                self,
                "Launcher Entry Added",
                "Muzic is now available in your applications menu.",
            )
    
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event."""
        self._closing = True
        if self._playlist_resolver and self._playlist_resolver.isRunning():
            self._playlist_resolver.requestInterruption()
            self._playlist_resolver.wait()

        # Save window state
        self.settings.window_maximized = self.isMaximized()
        if not self.isMaximized():
            self.settings.window_width = self.width()
            self.settings.window_height = self.height()
        
        # Save output directory
        self.settings.output_dir = self.output_dir_input.text().strip() or self.settings.output_dir
        
        self.settings_manager.save()
        
        # Cancel all downloads
        self.download_manager.shutdown()
        
        logger.info("Application closed")
        event.accept()


class SettingsDialog(QDialog):
    """Settings dialog."""
    
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumSize(640, 620)
        self.resize(700, 660)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Build a focused settings dialog with grouped, discoverable controls."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(16)

        title = QLabel("Settings")
        title.setObjectName("title")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(title)
        description = QLabel("Manage downloads, optional YouTube access, and local tools.")
        description.setObjectName("caption")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs, 1)

        general_content = QWidget()
        general_tab = QScrollArea()
        general_tab.setWidgetResizable(True)
        general_tab.setFrameShape(QFrame.Shape.NoFrame)
        general_tab.setWidget(general_content)
        general_layout = QVBoxLayout(general_content)
        general_layout.setContentsMargins(18, 18, 18, 18)
        general_layout.setSpacing(16)

        download_group = QGroupBox("Download behavior")
        download_form = QFormLayout(download_group)
        download_form.setContentsMargins(16, 22, 16, 16)
        download_form.setHorizontalSpacing(18)
        download_form.setVerticalSpacing(12)
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 10)
        self.parallel_spin.setValue(self.settings.max_parallel_downloads)
        self.parallel_spin.setMinimumHeight(44)
        self.parallel_spin.setToolTip("Number of downloads that may run at the same time.")
        download_form.addRow("Max parallel downloads", self.parallel_spin)

        tool_group = QGroupBox("Audio tools")
        tool_form = QFormLayout(tool_group)
        tool_form.setContentsMargins(16, 22, 16, 16)
        tool_form.setHorizontalSpacing(18)
        tool_form.setVerticalSpacing(12)
        
        self.ffmpeg_input = QLineEdit(self.settings.ffmpeg_path)
        self.ffmpeg_input.setMinimumHeight(44)
        self.ffmpeg_input.setPlaceholderText("ffmpeg on PATH, or full executable path")
        self.ffmpeg_input.setAccessibleName("FFmpeg executable path")
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(self.ffmpeg_input)
        self.ffmpeg_browse_button = QPushButton("Browse…")
        self.ffmpeg_browse_button.setObjectName("secondaryButton")
        self.ffmpeg_browse_button.clicked.connect(self._browse_ffmpeg)
        ffmpeg_row.addWidget(self.ffmpeg_browse_button)
        tool_form.addRow("FFmpeg path", ffmpeg_row)

        self.desktop_entry_button = QPushButton("Add Desktop Entry")
        self.desktop_entry_button.setObjectName("secondaryButton")
        self.desktop_entry_button.setToolTip("Add Muzic to your system applications menu.")
        self.desktop_entry_button.clicked.connect(self._add_desktop_entry)
        tool_form.addRow("Application launcher", self.desktop_entry_button)

        general_layout.addWidget(download_group)
        general_layout.addWidget(tool_group)
        general_layout.addStretch(1)
        self.tabs.addTab(general_tab, "General")

        services_content = QWidget()
        services_tab = QScrollArea()
        services_tab.setWidgetResizable(True)
        services_tab.setFrameShape(QFrame.Shape.NoFrame)
        services_tab.setWidget(services_content)
        services_layout = QVBoxLayout(services_content)
        services_layout.setContentsMargins(18, 18, 18, 18)
        services_layout.setSpacing(16)

        auth_group = QGroupBox("YouTube access")
        auth_form = QFormLayout(auth_group)
        auth_form.setContentsMargins(16, 22, 16, 16)
        auth_form.setHorizontalSpacing(18)
        auth_form.setVerticalSpacing(10)

        auth_intro = QLabel(
            "Authentication is off by default. Turn it on only if YouTube requires a signed-in session."
        )
        auth_intro.setObjectName("caption")
        auth_intro.setWordWrap(True)
        auth_form.addRow("", auth_intro)

        self.youtube_auth_combo = QComboBox()
        self.youtube_auth_combo.addItem("Off (recommended)", "none")
        self.youtube_auth_combo.addItem("Default browser session", "browser")
        self.youtube_auth_combo.addItem("Cookies file (advanced)", "file")
        auth_index = self.youtube_auth_combo.findData(
            getattr(self.settings, "youtube_auth_mode", "none")
        )
        self.youtube_auth_combo.setCurrentIndex(max(0, auth_index))
        self.youtube_auth_combo.setMinimumHeight(44)
        self.youtube_auth_combo.currentIndexChanged.connect(self._update_auth_controls)
        auth_form.addRow("Authentication", self.youtube_auth_combo)

        detected_browser = detect_default_browser()
        if detected_browser:
            self.default_browser_info = QLabel(
                f"Detected default browser: {detected_browser.title()}. "
                "Muzic will read its YouTube session only while this option is enabled."
            )
        else:
            self.default_browser_info = QLabel(
                "Muzic could not identify a supported default browser. Set a supported browser "
                "as the system default or use a cookies file."
            )
        self.default_browser_info.setWordWrap(True)
        auth_form.addRow("", self.default_browser_info)

        self.youtube_sign_in_button = QPushButton("Open YouTube in Default Browser")
        self.youtube_sign_in_button.setObjectName("secondaryButton")
        self.youtube_sign_in_button.clicked.connect(self._open_youtube_sign_in)
        auth_form.addRow("", self.youtube_sign_in_button)

        self.auth_privacy_note = QLabel(
            "First sign in to YouTube in the browser. With this option enabled, yt-dlp reads "
            "that browser's YouTube session for extraction. Muzic does not save or log cookie values. "
            "YouTube may still require verification or block requests."
        )
        self.auth_privacy_note.setWordWrap(True)
        self.auth_privacy_note.setObjectName("caption")
        auth_form.addRow("", self.auth_privacy_note)

        cookie_row = QHBoxLayout()
        self.youtube_cookies_input = QLineEdit(
            getattr(self.settings, "youtube_cookies_file", "")
        )
        self.youtube_cookies_input.setMinimumHeight(44)
        self.youtube_cookies_input.setPlaceholderText("Netscape-format cookies file")
        self.youtube_cookies_input.setAccessibleName("YouTube cookies file path")
        cookie_row.addWidget(self.youtube_cookies_input)
        self.youtube_cookies_browse_button = QPushButton("Browse…")
        self.youtube_cookies_browse_button.setObjectName("secondaryButton")
        self.youtube_cookies_browse_button.clicked.connect(self._browse_cookies)
        cookie_row.addWidget(self.youtube_cookies_browse_button)
        auth_form.addRow("Cookies file", cookie_row)

        runtime_group = QGroupBox("JavaScript runtime")
        runtime_form = QFormLayout(runtime_group)
        runtime_form.setContentsMargins(16, 22, 16, 16)
        runtime_form.setHorizontalSpacing(18)
        runtime_form.setVerticalSpacing(10)

        self.use_deno_checkbox = QCheckBox("Use Deno when available")
        self.use_deno_checkbox.setChecked(
            getattr(self.settings, "use_deno_runtime", False)
        )
        self.use_deno_checkbox.stateChanged.connect(self._update_deno_controls)
        runtime_form.addRow("Optional support", self.use_deno_checkbox)

        self.deno_input = QLineEdit(getattr(self.settings, "deno_path", ""))
        self.deno_input.setMinimumHeight(44)
        self.deno_input.setPlaceholderText("deno on PATH, or full executable path")
        self.deno_input.setAccessibleName("Deno executable path")
        self.deno_input.editingFinished.connect(self._refresh_deno_status)
        deno_row = QHBoxLayout()
        deno_row.addWidget(self.deno_input)
        self.deno_browse_button = QPushButton("Browse…")
        self.deno_browse_button.setObjectName("secondaryButton")
        self.deno_browse_button.clicked.connect(self._browse_deno)
        deno_row.addWidget(self.deno_browse_button)
        runtime_form.addRow("Deno path", deno_row)

        self.deno_status_label = QLabel()
        self.deno_status_label.setWordWrap(True)
        runtime_form.addRow("Status", self.deno_status_label)

        services_layout.addWidget(auth_group)
        services_layout.addWidget(runtime_group)
        services_layout.addStretch(1)
        self.tabs.addTab(services_tab, "YouTube & Runtime")

        self._update_auth_controls()
        self._update_deno_controls()
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_ffmpeg(self) -> None:
        """Choose an FFmpeg executable for the configured path."""
        current_path = self.ffmpeg_input.text().strip()
        current = Path(current_path).expanduser() if current_path else Path.home()
        start_directory = str(current if current.is_dir() else current.parent)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select FFmpeg Executable",
            start_directory,
            "FFmpeg executable (ffmpeg.exe);;Executable files (*.exe);;All files (*)",
        )
        if file_path:
            self.ffmpeg_input.setText(file_path)

    def _browse_cookies(self) -> None:
        current = self.youtube_cookies_input.text().strip()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select YouTube Cookies File",
            str(Path(current).expanduser().parent) if current else str(Path.home()),
            "Cookies files (*.txt *.cookies);;All files (*)",
        )
        if file_path:
            self.youtube_cookies_input.setText(file_path)

    def _browse_deno(self) -> None:
        """Choose the Deno executable used by yt-dlp."""
        current = Path(self.deno_input.text()).expanduser() if self.deno_input.text().strip() else Path.home()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Deno Executable",
            str(current if current.is_dir() else current.parent),
            "Deno executable (deno, deno.exe);;All files (*)",
        )
        if file_path:
            self.deno_input.setText(file_path)
            self._refresh_deno_status()

    def _refresh_deno_status(self, *_args) -> None:
        """Show Deno status while making clear that it is optional."""
        if not self.use_deno_checkbox.isChecked():
            message = "Deno is disabled. Downloads will continue without a JavaScript runtime."
            self.deno_status_label.setText(message)
            self.deno_status_label.setStyleSheet("color: #B3B3B3;")
            self.deno_status_label.setToolTip(message)
            return

        executable, version, error = deno_runtime_status(
            self.settings,
            deno_path=self.deno_input.text(),
        )
        if error:
            message = f"{error} Downloads will continue without Deno; some YouTube formats may be unavailable."
            self.deno_status_label.setText(message)
            self.deno_status_label.setStyleSheet("color: #FFA726;")
            self.deno_status_label.setToolTip(message)
            return

        status = f"Deno {version} is ready."
        self.deno_status_label.setText(status)
        self.deno_status_label.setStyleSheet("color: #22C55E;")
        self.deno_status_label.setToolTip(executable)

    def _update_deno_controls(self, *_args) -> None:
        enabled = self.use_deno_checkbox.isChecked()
        self.deno_input.setEnabled(enabled)
        self.deno_browse_button.setEnabled(enabled)
        self._refresh_deno_status()

    def _update_auth_controls(self, *_args) -> None:
        mode = self.youtube_auth_combo.currentData()
        self.default_browser_info.setVisible(mode == "browser")
        self.youtube_sign_in_button.setVisible(mode == "browser")
        self.auth_privacy_note.setVisible(mode == "browser")
        self.youtube_cookies_input.setEnabled(mode == "file")
        self.youtube_cookies_browse_button.setEnabled(mode == "file")

    def _open_youtube_sign_in(self) -> None:
        """Open YouTube in the OS default browser so the user can sign in there."""
        if not QDesktopServices.openUrl(QUrl("https://music.youtube.com/")):
            QMessageBox.warning(
                self,
                "Could Not Open Browser",
                "Open YouTube Music in your default browser, sign in, then retry the download.",
            )

    def _add_desktop_entry(self) -> None:
        """Create a current-user launcher entry for the current platform."""
        try:
            _create_desktop_entry_for_current_user()
        except (OSError, subprocess.SubprocessError) as error:
            QMessageBox.critical(self, "Launcher Entry Failed", str(error))
            return

        QMessageBox.information(
            self,
            "Launcher Entry Added",
            "Muzic is now available in your applications menu.",
        )

    def accept(self) -> None:
        """Save settings and close."""
        self.settings.max_parallel_downloads = self.parallel_spin.value()
        self.settings.ffmpeg_path = self.ffmpeg_input.text().strip() or ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        self.settings.youtube_auth_mode = self.youtube_auth_combo.currentData()
        self.settings.youtube_cookies_file = self.youtube_cookies_input.text().strip()
        self.settings.deno_path = self.deno_input.text().strip()
        self.settings.use_deno_runtime = self.use_deno_checkbox.isChecked()

        valid, errors = self.settings.validate()
        if not valid:
            QMessageBox.warning(self, "Invalid Settings", "\n".join(errors))
            return

        super().accept()


class ManagePlaylistsDialog(QDialog):
    """Dialog to manage saved playlists in a table format."""

    def __init__(
        self,
        playlist_folders: dict[str, str],
        playlist_urls: dict[str, str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._original_folders = playlist_folders
        # Work on copies so Cancel can discard changes
        self._folders: dict[str, str] = dict(playlist_folders)
        self._urls: dict[str, str] = dict(playlist_urls or {})

        self.setWindowTitle("Manage Saved Playlists")
        self.setMinimumWidth(1000)
        self.setMinimumHeight(600)

        self._setup_ui()
        self._populate_table()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Table widget for playlists
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(3)
        self.table_widget.setHorizontalHeaderLabels(["Name", "Folder Path", "Playlist URL"])
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table_widget)

        # Buttons row
        button_row = QHBoxLayout()

        self.add_button = QPushButton("Add Playlist")
        self.add_button.clicked.connect(self._on_add_clicked)
        button_row.addWidget(self.add_button)

        self.browse_button = QPushButton("Browse Folder...")
        self.browse_button.clicked.connect(self._on_browse_clicked)
        button_row.addWidget(self.browse_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.clicked.connect(self._on_delete_clicked)
        button_row.addWidget(self.delete_button)

        button_row.addStretch()

        layout.addLayout(button_row)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_table(self) -> None:
        """Populate table with playlist data."""
        self.table_widget.blockSignals(True)
        self.table_widget.setRowCount(0)

        for name in sorted(self._folders.keys()):
            row = self.table_widget.rowCount()
            self.table_widget.insertRow(row)

            # Name column
            name_item = QTableWidgetItem(name)
            self.table_widget.setItem(row, 0, name_item)

            # Folder path column
            path = self._folders[name]
            path_item = QTableWidgetItem(path)
            self.table_widget.setItem(row, 1, path_item)

            # URL column
            url = self._urls.get(name, "")
            url_item = QTableWidgetItem(url)
            self.table_widget.setItem(row, 2, url_item)

        self.table_widget.blockSignals(False)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Handle inline editing of table items."""
        row = item.row()
        col = item.column()

        # Get the original name (stored in column 0)
        name_item = self.table_widget.item(row, 0)
        if not name_item:
            return

        new_value = item.text().strip()

        # Find the original name by searching through our data
        sorted_names = sorted(self._folders.keys())
        if row >= len(sorted_names):
            return
        old_name = sorted_names[row]

        if col == 0:  # Name column
            if not new_value:
                QMessageBox.warning(self, "Invalid Name", "Playlist name cannot be empty.")
                self._populate_table()
                return

            if new_value != old_name:
                if new_value in self._folders:
                    QMessageBox.warning(self, "Name Exists", "A playlist with this name already exists.")
                    self._populate_table()
                    return

                # Rename the playlist
                path = self._folders.pop(old_name)
                self._folders[new_value] = path

                if old_name in self._urls:
                    url_value = self._urls.pop(old_name)
                    self._urls[new_value] = url_value

                self._populate_table()

        elif col == 1:  # Folder path column
            self._folders[old_name] = new_value

        elif col == 2:  # URL column
            if new_value:
                self._urls[old_name] = new_value
            else:
                self._urls.pop(old_name, None)

    def _on_add_clicked(self) -> None:
        """Add a new playlist entry."""
        name, ok = QInputDialog.getText(
            self,
            "Add Playlist",
            "Playlist name:",
        )
        if not ok:
            return

        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Playlist name cannot be empty.")
            return

        if name in self._folders:
            QMessageBox.warning(self, "Name Exists", "A playlist with this name already exists.")
            return

        # Ask for folder path
        folder_path, ok_path = QInputDialog.getText(
            self,
            "Add Playlist",
            "Folder path:",
        )
        if not ok_path:
            return

        folder_path = folder_path.strip()
        if not folder_path:
            QMessageBox.warning(self, "Invalid Path", "Folder path cannot be empty.")
            return

        # Ask for URL (optional)
        url, ok_url = QInputDialog.getText(
            self,
            "Add Playlist",
            "Playlist URL (optional):",
        )
        if not ok_url:
            url = ""

        # Add to data
        self._folders[name] = folder_path
        url = url.strip()
        if url:
            self._urls[name] = url

        self._populate_table()

    def _on_browse_clicked(self) -> None:
        """Browse for folder path for selected playlist."""
        current_row = self.table_widget.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "No Selection", "Please select a playlist row first.")
            return

        # Get current folder path from the selected row
        path_item = self.table_widget.item(current_row, 1)
        current_path = path_item.text() if path_item else ""

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Folder",
            current_path
        )

        if directory:
            # Update the table cell
            path_item.setText(directory)

            # Update the data
            sorted_names = sorted(self._folders.keys())
            if current_row < len(sorted_names):
                name = sorted_names[current_row]
                self._folders[name] = directory

    def _on_delete_clicked(self) -> None:
        """Delete selected playlist."""
        current_row = self.table_widget.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "No Selection", "Please select a playlist to delete.")
            return

        sorted_names = sorted(self._folders.keys())
        if current_row >= len(sorted_names):
            return

        name = sorted_names[current_row]

        reply = QMessageBox.question(
            self,
            "Delete Playlist",
            f"Delete saved playlist '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._folders.pop(name, None)
        self._urls.pop(name, None)
        self._populate_table()

    def get_playlist_folders(self) -> dict[str, str]:
        """Return the modified playlist-folder mapping."""
        return dict(self._folders)

    def get_playlist_urls(self) -> dict[str, str]:
        """Return the modified playlist-URL mapping."""
        return dict(self._urls)
