"""Muzic - Modern Music Downloader
Main application entry point.
"""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from .ui.main_window import MainWindow
from .utils.logger import logger
from .config.constants import APP_NAME


def main() -> int:
    """Application main entry point."""
    try:
        # Enable High DPI scaling
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        
        # Create application
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setOrganizationName("Muzic")
        
        # Create and show main window
        window = MainWindow()
        window.show()
        
        # Run application
        return app.exec()
    
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
