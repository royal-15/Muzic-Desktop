"""Main application window."""
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QComboBox, QLabel,
    QTableWidget, QTableWidgetItem, QProgressBar,
    QFileDialog, QHeaderView, QMessageBox, QSpinBox,
    QDialog, QFormLayout, QDialogButtonBox, QInputDialog,
    QListWidget, QListWidgetItem, QToolButton, QMenu
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QCloseEvent

from ..config.settings import SettingsManager
from ..config.constants import (
    APP_NAME, APP_VERSION, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
    WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT,
    QUALITY_OPTIONS, FORMAT_OPTIONS,
    STATUS_QUEUED, STATUS_DOWNLOADING, STATUS_COMPLETED, STATUS_FAILED,
)
from ..core.download_manager import DownloadManager
from ..core.download_worker import DownloadTask
from ..utils.validators import parse_multiple_urls, is_valid_directory, is_valid_url, is_youtube_url
from ..utils.logger import logger
from .styles.theme import Theme
from .components.toast import Toast


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        # Load settings
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.settings
        
        # Initialize theme
        self.theme = Theme(self.settings.theme)
        
        # Initialize download manager
        self.download_manager = DownloadManager(self.settings, self)
        
        # Setup UI
        self._setup_window()
        self._setup_ui()
        self._apply_theme()
        self._connect_signals()
        
        # Show disclaimer if first run
        if self.settings.first_run:
            self._show_disclaimer()

        logger.info(f"{APP_NAME} v{APP_VERSION} started")
    
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
        
        # Input section
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)
        
        # URL/Search input
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste URL or enter song name...")
        self.url_input.returnPressed.connect(self._on_add_clicked)
        input_layout.addWidget(self.url_input, 3)

        self.input_file_button = QPushButton("Browse .txt")
        self.input_file_button.setObjectName("secondaryButton")
        self.input_file_button.clicked.connect(self._on_browse_input_file_clicked)
        self.input_file_button.setVisible(False)
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
        input_layout.addWidget(self.mode_combo, 1)
        
        # Quality selector
        quality_label = QLabel("Quality:")
        input_layout.addWidget(quality_label)
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(QUALITY_OPTIONS)
        self.quality_combo.setCurrentText(self.settings.default_quality)
        self.quality_combo.currentTextChanged.connect(self._on_quality_changed)
        input_layout.addWidget(self.quality_combo)
        
        # Format selector
        format_label = QLabel("Format:")
        input_layout.addWidget(format_label)
        
        self.format_combo = QComboBox()
        self.format_combo.addItems(FORMAT_OPTIONS)
        self.format_combo.setCurrentText(self.settings.default_format)
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        input_layout.addWidget(self.format_combo)
        
        # Add button
        self.add_button = QPushButton("Add to Queue")
        self.add_button.clicked.connect(self._on_add_clicked)
        input_layout.addWidget(self.add_button)
        
        main_layout.addLayout(input_layout)
        
        # Queue table
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(6)
        self.queue_table.setHorizontalHeaderLabels([
            "ID", "URL", "Status", "Progress", "Speed", "ETA"
        ])
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.queue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.queue_table.setAlternatingRowColors(True)
        main_layout.addWidget(self.queue_table, 1)
        
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

        self.save_playlist_button = QPushButton("Save Playlist Folder")
        self.save_playlist_button.setObjectName("secondaryButton")
        self.save_playlist_button.clicked.connect(self._on_save_playlist_folder_clicked)
        bottom_row_layout.addWidget(self.save_playlist_button)

        self.manage_playlists_button = QPushButton("Manage...")
        self.manage_playlists_button.setObjectName("secondaryButton")
        self.manage_playlists_button.clicked.connect(self._on_manage_playlist_folders_clicked)
        bottom_row_layout.addWidget(self.manage_playlists_button)

        bottom_row_layout.addStretch()

        # Right section: queue controls
        self.start_all_button = QPushButton("Start All")
        self.start_all_button.clicked.connect(self._on_start_all_clicked)
        bottom_row_layout.addWidget(self.start_all_button)

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
        
        # Status bar
        self.statusBar().showMessage("Ready")
    
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
        query_text = self.url_input.text().strip()
        mode = self.mode_combo.currentText()
        
        if not query_text:
            if mode == "From .txt":
                Toast.show_message(self, "Please select a .txt file", "warning")
            else:
                Toast.show_message(self, "Please enter a URL or search query", "warning")
            return
        
        # Update settings
        self.settings.output_dir = self.output_dir_input.text().strip() or self.settings.output_dir
        self.settings_manager.save()
        
        # Process query based on mode
        queries = self._process_query(query_text, mode)
        
        if not queries:
            Toast.show_message(self, "No valid URLs or queries found", "error")
            return
        
        # Add tasks
        self.download_manager.add_tasks(queries)
        
        # Clear input
        self.url_input.clear()
        
        Toast.show_message(self, f"Added {len(queries)} download(s) to queue", "success")
    
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
                # Use yt-dlp search syntax
                return [f"ytsearch1:{text}"]
        else:
            if is_valid_url(text):
                Toast.show_message(self, "Only YouTube URLs are supported", "error", 3000)
                return []

            # No valid URLs, treat as search query
            if mode == "Auto" or mode == "Search on YouTube":
                # Default to YouTube search
                return [f"ytsearch1:{text}"]
            elif mode == "YouTube URL":
                # Must be a URL in this mode
                return []
        
        return []

    def _process_txt_file(self, file_path: str) -> list[str]:
        """Read a .txt batch file and convert each line to a download query."""
        path = Path(file_path).expanduser()

        if path.suffix.lower() != ".txt":
            Toast.show_message(self, "Please select a .txt file", "error", 3000)
            return []

        if not path.is_file():
            Toast.show_message(self, "Text file not found", "error", 3000)
            return []

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            Toast.show_message(self, f"Could not read file: {e}", "error", 4000)
            return []

        queries = []
        seen = set()

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line in seen:
                continue

            if is_youtube_url(line):
                query = line
            elif is_valid_url(line):
                continue
            else:
                query = f"ytsearch1:{line}"

            seen.add(line)
            queries.append(query)

        if not queries:
            Toast.show_message(self, "No YouTube URLs or search names found in file", "error", 4000)

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
            Toast.show_message(self, f"Loaded playlist '{name}' - Click 'Add to Queue' to download", "info", 3000)
        else:
            Toast.show_message(self, f"Output folder set for '{name}'", "info", 2000)

    def _on_save_playlist_folder_clicked(self) -> None:
        """Save the current output directory under a playlist name."""
        directory = self.output_dir_input.text().strip()
        if not directory:
            Toast.show_message(self, "Please select an output directory first", "warning", 3000)
            return

        is_valid, error_message = is_valid_directory(directory)
        if not is_valid:
            Toast.show_message(self, error_message, "error", 3000)
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
            Toast.show_message(self, "Playlist name cannot be empty", "warning", 3000)
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

        Toast.show_message(self, f"Saved folder for playlist '{name}'", "success", 3000)

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
            Toast.show_message(self, "Updated saved playlists", "success", 2000)
        
    def _on_start_all_clicked(self) -> None:
        """Handle start all button click."""
        self.download_manager.start_all_queued()
    
    def _on_cancel_all_clicked(self) -> None:
        """Handle cancel all button click."""
        self.download_manager.cancel_all()
        Toast.show_message(self, "Cancelled all downloads", "info")
    
    def _on_clear_completed_clicked(self) -> None:
        """Handle clear completed button click."""
        self.download_manager.clear_completed()
        Toast.show_message(self, "Cleared completed downloads", "info", 2000)
    
    def _on_clear_failed_clicked(self) -> None:
        """Handle clear failed button click."""
        self.download_manager.clear_failed()
        Toast.show_message(self, "Cleared failed downloads", "info", 2000)
    
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
            Toast.show_message(self, "Cleared all downloads", "info", 2000)
    
    def _on_settings_clicked(self) -> None:
        """Handle settings button click."""
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings_manager.save()
            self.output_dir_input.setText(self.settings.output_dir)
            Toast.show_message(self, "Settings saved", "success")
    
    def _on_task_added(self, task: DownloadTask) -> None:
        """Handle new task added."""
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)
        
        self.queue_table.setItem(row, 0, QTableWidgetItem(str(task.id)))

        display_text, tooltip = self._get_task_display_and_tooltip(task)
        url_item = QTableWidgetItem(display_text)
        if tooltip:
            url_item.setToolTip(tooltip)
        self.queue_table.setItem(row, 1, url_item)

        self.queue_table.setItem(row, 2, QTableWidgetItem(task.status.capitalize()))
        
        progress_bar = QProgressBar()
        progress_bar.setValue(task.progress)
        self.queue_table.setCellWidget(row, 3, progress_bar)
        
        self.queue_table.setItem(row, 4, QTableWidgetItem(task.speed))
        self.queue_table.setItem(row, 5, QTableWidgetItem(task.eta))
    
    def _on_task_updated(self, task: DownloadTask) -> None:
        """Handle task update."""
        # Find task row
        for row in range(self.queue_table.rowCount()):
            id_item = self.queue_table.item(row, 0)
            if id_item and int(id_item.text()) == task.id:
                # Update status
                status_item = self.queue_table.item(row, 2)
                if status_item:
                    status_item.setText(task.status.capitalize())
                
                # Update progress bar
                progress_bar = self.queue_table.cellWidget(row, 3)
                if isinstance(progress_bar, QProgressBar):
                    progress_bar.setValue(task.progress)
                
                # Update speed and ETA
                speed_item = self.queue_table.item(row, 4)
                if speed_item:
                    speed_item.setText(task.speed or "")
                
                eta_item = self.queue_table.item(row, 5)
                if eta_item:
                    eta_item.setText(task.eta or "")
                
                break
    
    def _on_task_completed(self, task: DownloadTask) -> None:
        """Handle task completion."""
        logger.info(f"Task {task.id} completed")
        Toast.show_message(self, "Download completed!", "success", 2000)
    
    def _on_task_failed(self, task: DownloadTask) -> None:
        """Handle task failure."""
        logger.error(f"Task {task.id} failed: {task.error_message}")
        Toast.show_message(self, f"Download failed: {task.error_message[:50]}", "error", 4000)
    
    def _refresh_table(self) -> None:
        """Rebuild the queue table from current tasks."""
        # Clear the table
        self.queue_table.setRowCount(0)
        
        # Rebuild from download manager tasks
        all_tasks = self.download_manager.get_all_tasks()
        for task in all_tasks:
            row = self.queue_table.rowCount()
            self.queue_table.insertRow(row)
            
            self.queue_table.setItem(row, 0, QTableWidgetItem(str(task.id)))

            display_text, tooltip = self._get_task_display_and_tooltip(task)
            url_item = QTableWidgetItem(display_text)
            if tooltip:
                url_item.setToolTip(tooltip)
            self.queue_table.setItem(row, 1, url_item)

            self.queue_table.setItem(row, 2, QTableWidgetItem(task.status.capitalize()))
            
            progress_bar = QProgressBar()
            progress_bar.setValue(task.progress)
            self.queue_table.setCellWidget(row, 3, progress_bar)
            
            self.queue_table.setItem(row, 4, QTableWidgetItem(task.speed or ""))
            self.queue_table.setItem(row, 5, QTableWidgetItem(task.eta or ""))
    
    def _update_stats(self) -> None:
        """Update status bar with statistics."""
        stats = self.download_manager.get_stats()
        status_text = f"Total: {stats['total']} | Downloading: {stats['downloading']} | Completed: {stats['completed']} | Failed: {stats['failed']}"
        self.statusBar().showMessage(status_text)
    
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
    
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event."""
        # Save window state
        self.settings.window_maximized = self.isMaximized()
        if not self.isMaximized():
            self.settings.window_width = self.width()
            self.settings.window_height = self.height()
        
        # Save output directory
        self.settings.output_dir = self.output_dir_input.text().strip() or self.settings.output_dir
        
        self.settings_manager.save()
        
        # Cancel all downloads
        self.download_manager.cancel_all()
        
        logger.info("Application closed")
        event.accept()


class SettingsDialog(QDialog):
    """Settings dialog."""
    
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup dialog UI."""
        layout = QFormLayout(self)
        
        # Max parallel downloads
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 10)
        self.parallel_spin.setValue(self.settings.max_parallel_downloads)
        layout.addRow("Max Parallel Downloads:", self.parallel_spin)
        
        # Tool paths
        self.yt_dlp_input = QLineEdit(self.settings.yt_dlp_path)
        layout.addRow("yt-dlp Path:", self.yt_dlp_input)
        
        self.ffmpeg_input = QLineEdit(self.settings.ffmpeg_path)
        layout.addRow("FFmpeg Path:", self.ffmpeg_input)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def accept(self) -> None:
        """Save settings and close."""
        self.settings.max_parallel_downloads = self.parallel_spin.value()
        self.settings.yt_dlp_path = self.yt_dlp_input.text().strip() or "yt-dlp"
        self.settings.ffmpeg_path = self.ffmpeg_input.text().strip() or "ffmpeg"

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
        self.table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_widget.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
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
