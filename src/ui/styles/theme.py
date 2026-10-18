"""Theme system for generating Qt Style Sheets."""
from typing import Dict
from ...config.constants import (
    COLORS_DARK,
    COLORS_LIGHT,
    FONT_FAMILY,
    FONT_SIZE_BODY,
    FONT_SIZE_SUBTITLE,
    PADDING,
    MARGIN,
    BORDER_RADIUS,
)


class Theme:
    """Theme manager for generating QSS stylesheets."""
    
    def __init__(self, theme_name: str = "dark"):
        self.theme_name = theme_name
        self.colors = COLORS_DARK if theme_name == "dark" else COLORS_LIGHT
    
    def get_stylesheet(self) -> str:
        """Generate complete application stylesheet."""
        return f"""
/* Global styles */
QWidget {{
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_BODY}px;
    color: {self.colors['text_primary']};
    background-color: {self.colors['background']};
}}

/* Main Window */
QMainWindow {{
    background-color: {self.colors['background']};
}}

/* Scrollbars */
QScrollBar:vertical {{
    border: none;
    background: {self.colors['surface']};
    width: 12px;
    border-radius: 6px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background: {self.colors['text_secondary']};
    min-height: 20px;
    border-radius: 6px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background: {self.colors['primary']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    border: none;
    background: {self.colors['surface']};
    height: 12px;
    border-radius: 6px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background: {self.colors['text_secondary']};
    min-width: 20px;
    border-radius: 6px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {self.colors['primary']};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* Buttons */
QPushButton {{
    background-color: {self.colors['primary']};
    color: {self.colors['text_primary']};
    border: none;
    padding: 10px 20px;
    border-radius: {BORDER_RADIUS}px;
    font-weight: 600;
    font-size: {FONT_SIZE_BODY}px;
}}

QPushButton:hover {{
    background-color: #1ED760;
}}

QPushButton:pressed {{
    background-color: #1AA34A;
}}

QPushButton:disabled {{
    background-color: {self.colors['text_disabled']};
    color: {self.colors['text_secondary']};
}}

QPushButton#secondaryButton {{
    background-color: {self.colors['card']};
    color: {self.colors['text_primary']};
    border: 1px solid {self.colors['border']};
}}

QPushButton#secondaryButton:hover {{
    background-color: {self.colors['card_hover']};
}}

QPushButton#dangerButton {{
    background-color: {self.colors['error']};
}}

QPushButton#dangerButton:hover {{
    background-color: #F44336;
}}

/* Line Edit / Input Fields */
QLineEdit {{
    background-color: {self.colors['input_bg']};
    color: {self.colors['text_primary']};
    border: 2px solid {self.colors['border']};
    border-radius: {BORDER_RADIUS}px;
    padding: 10px 16px;
    font-size: {FONT_SIZE_BODY}px;
}}

QLineEdit:focus {{
    border-color: {self.colors['primary']};
}}

QLineEdit:disabled {{
    background-color: {self.colors['surface']};
    color: {self.colors['text_disabled']};
}}

/* Combo Box */
QComboBox {{
    background-color: {self.colors['input_bg']};
    color: {self.colors['text_primary']};
    border: 2px solid {self.colors['border']};
    border-radius: {BORDER_RADIUS}px;
    padding: 8px 16px;
    padding-right: 36px;
    font-size: {FONT_SIZE_BODY}px;
}}

QComboBox:hover {{
    border-color: {self.colors['primary']};
}}

QComboBox:focus {{
    border-color: {self.colors['primary']};
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid {self.colors['text_secondary']};
    margin-right: 10px;
}}

QComboBox QAbstractItemView {{
    background-color: {self.colors['card']};
    color: {self.colors['text_primary']};
    border: 1px solid {self.colors['border']};
    border-radius: {BORDER_RADIUS}px;
    selection-background-color: {self.colors['primary']};
    selection-color: white;
    padding: 4px;
}}

/* Progress Bar */
QProgressBar {{
    background-color: {self.colors['surface']};
    border: none;
    border-radius: {BORDER_RADIUS // 2}px;
    height: 8px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {self.colors['primary']};
    border-radius: {BORDER_RADIUS // 2}px;
}}

/* Table Widget */
QTableWidget {{
    background-color: {self.colors['surface']};
    alternate-background-color: {self.colors['card']};
    border: none;
    gridline-color: {self.colors['border']};
}}

QTableWidget::item {{
    padding: 8px;
    border: none;
}}

QTableWidget::item:selected {{
    background-color: {self.colors['primary']};
    color: white;
}}

QHeaderView::section {{
    background-color: {self.colors['card']};
    color: {self.colors['text_primary']};
    padding: 10px;
    border: none;
    border-bottom: 2px solid {self.colors['border']};
    font-weight: 600;
}}

/* Spin Box */
QSpinBox {{
    background-color: {self.colors['input_bg']};
    color: {self.colors['text_primary']};
    border: 2px solid {self.colors['border']};
    border-radius: {BORDER_RADIUS}px;
    padding: 8px 12px;
}}

QSpinBox:focus {{
    border-color: {self.colors['primary']};
}}

QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {self.colors['card']};
    border: none;
    width: 20px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: {self.colors['primary']};
}}

/* Labels */
QLabel {{
    color: {self.colors['text_primary']};
    background: transparent;
}}

QLabel#subtitle {{
    font-size: {FONT_SIZE_SUBTITLE}px;
    font-weight: 600;
}}

QLabel#caption {{
    color: {self.colors['text_secondary']};
    font-size: 12px;
}}

QStatusBar {{
    background-color: {self.colors['surface']};
    color: {self.colors['text_secondary']};
    border-top: 1px solid {self.colors['border']};
    padding: 3px 6px;
}}

QStatusBar::item {{
    border: none;
}}

QLabel#statusMessage {{
    color: {self.colors['text_secondary']};
    padding: 2px 6px;
}}

QWidget#queueStatusCounts QLabel#queueCount {{
    color: {self.colors['text_secondary']};
    font-size: 11px;
    padding: 2px 0;
}}

QWidget#queueStatusCounts QLabel#queueCountFailed {{
    color: {self.colors['text_secondary']};
    font-size: 11px;
    padding: 2px 0;
}}

QWidget#queueStatusCounts QLabel#queueCountFailed[attention="true"] {{
    color: {self.colors['error']};
    font-weight: 600;
}}

/* Dialog */
QDialog {{
    background-color: {self.colors['background']};
}}

/* Menu Bar */
QMenuBar {{
    background-color: {self.colors['surface']};
    color: {self.colors['text_primary']};
}}

QMenuBar::item:selected {{
    background-color: {self.colors['primary']};
}}

QMenu {{
    background-color: {self.colors['card']};
    color: {self.colors['text_primary']};
    border: 1px solid {self.colors['border']};
}}

QMenu::item:selected {{
    background-color: {self.colors['primary']};
}}

/* Group Box */
QGroupBox {{
    border: 2px solid {self.colors['border']};
    border-radius: {BORDER_RADIUS}px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}}

/* Check Box */
QCheckBox {{
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 20px;
    height: 20px;
    border: 2px solid {self.colors['border']};
    border-radius: 4px;
    background-color: {self.colors['input_bg']};
}}

QCheckBox::indicator:checked {{
    background-color: {self.colors['primary']};
    border-color: {self.colors['primary']};
}}

QCheckBox::indicator:hover {{
    border-color: {self.colors['primary']};
}}

/* Radio Button */
QRadioButton {{
    spacing: 8px;
}}

QRadioButton::indicator {{
    width: 20px;
    height: 20px;
    border: 2px solid {self.colors['border']};
    border-radius: 10px;
    background-color: {self.colors['input_bg']};
}}

QRadioButton::indicator:checked {{
    background-color: {self.colors['primary']};
    border-color: {self.colors['primary']};
}}

/* Tab Widget */
QTabWidget::pane {{
    border: 1px solid {self.colors['border']};
    border-radius: {BORDER_RADIUS}px;
    background-color: {self.colors['surface']};
}}

QTabBar::tab {{
    background-color: {self.colors['card']};
    color: {self.colors['text_secondary']};
    border: none;
    padding: 10px 20px;
    margin-right: 4px;
    border-top-left-radius: {BORDER_RADIUS}px;
    border-top-right-radius: {BORDER_RADIUS}px;
}}

QTabBar::tab:selected {{
    background-color: {self.colors['surface']};
    color: {self.colors['text_primary']};
    font-weight: 600;
}}

QTabBar::tab:hover {{
    background-color: {self.colors['card_hover']};
}}

/* Tool Tip */
QToolTip {{
    background-color: {self.colors['card']};
    color: {self.colors['text_primary']};
    border: 1px solid {self.colors['border']};
    border-radius: {BORDER_RADIUS}px;
    padding: 6px 10px;
}}

/* Status indicators */
.status-queued {{
    color: {self.colors['text_secondary']};
}}

.status-downloading {{
    color: {self.colors['info']};
}}

.status-completed {{
    color: {self.colors['success']};
}}

.status-failed {{
    color: {self.colors['error']};
}}

.status-paused {{
    color: {self.colors['warning']};
}}
"""
    
    def get_card_style(self) -> str:
        """Get style for card-like containers."""
        return f"""
background-color: {self.colors['card']};
border-radius: {BORDER_RADIUS}px;
padding: {PADDING}px;
"""
    
    def switch_theme(self, theme_name: str) -> None:
        """Switch between dark and light themes."""
        self.theme_name = theme_name
        self.colors = COLORS_DARK if theme_name == "dark" else COLORS_LIGHT
