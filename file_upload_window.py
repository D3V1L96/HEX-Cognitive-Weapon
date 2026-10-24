import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QListWidget, QListWidgetItem, QGraphicsDropShadowEffect, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import QFont, QDragEnterEvent, QDropEvent, QColor

logging.basicConfig(level=logging.INFO, format='[FileUI] %(message)s')
logger = logging.getLogger(__name__)


class GlassPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            GlassPanel {
                background-color: rgba(10, 20, 30, 200);
                border: 1px solid rgba(100, 180, 255, 40);
                border-radius: 12px;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 150, 255, 50))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)


class FileUploadWindow(QWidget):
    """Professional File Upload Window matching HEX HUD design."""
    file_uploaded = pyqtSignal(str)

    SUPPORTED_FORMATS = (
        "All Supported (*.txt *.py *.js *.ts *.cpp *.c *.h *.java *.cs "
        "*.html *.css *.json *.csv *.xml *.yaml *.yml *.md *.log *.cfg "
        "*.ini *.env *.sql *.sh *.bat *.ps1 *.pdf *.docx *.pptx "
        "*.jpg *.jpeg *.png *.gif *.webp *.bmp *.mp3 *.wav *.mp4 *.avi "
        "*.zip *.tar *.gz *.xlsx *.xls)"
    )
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("H.E.X // File Upload")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        # ✅ Solid dark background - NO translucency (prevents black screen)
        self.setStyleSheet("QWidget { background-color: rgb(12, 22, 35); }")
        self.setMinimumSize(460, 520)
        self.resize(480, 560)
        self.setAcceptDrops(True)
        self._drag_pos = None
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)

        container = GlassPanel()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(16, 16, 16, 16)
        cl.setSpacing(12)

        # Title Bar
        title_row = QHBoxLayout()
        title = QLabel("📁 FILE UPLOAD")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0f4ff; letter-spacing: 3px;")
        title_row.addWidget(title)
        title_row.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { background: rgba(255,80,80,60); color: #ffcccc; border: none;
                border-radius: 15px; font-size: 14px; font-weight: bold; }
            QPushButton:hover { background: rgba(255,80,80,150); }
        """)
        close_btn.clicked.connect(self.hide)
        title_row.addWidget(close_btn)
        cl.addLayout(title_row)

        # Drop Zone
        self.drop_zone = QLabel("🎯 Drag & Drop Files Here\nor Click Browse Below")
        self.drop_zone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_zone.setMinimumHeight(110)
        self.drop_zone.setWordWrap(True)
        self.drop_zone.setFont(QFont("Segoe UI", 12))
        self.drop_zone.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 180, 255, 15);
                border: 2px dashed rgba(100, 180, 255, 50);
                border-radius: 10px; color: #87ceeb; padding: 20px;
            }
        """)
        self.drop_zone.setCursor(Qt.CursorShape.PointingHandCursor)
        cl.addWidget(self.drop_zone)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        browse_btn = QPushButton("📂 BROWSE")
        self._style_btn(browse_btn, "#1e4d6b", "#2a6a8f")
        browse_btn.clicked.connect(self._browse_files)
        btn_row.addWidget(browse_btn)

        clear_btn = QPushButton("🗑️ CLEAR")
        self._style_btn(clear_btn, "#6b1e1e", "#8f2a2a")
        clear_btn.clicked.connect(self._clear_files)
        btn_row.addWidget(clear_btn)
        cl.addLayout(btn_row)

        # File List Header
        list_label = QLabel("UPLOADED FILES")
        list_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        list_label.setStyleSheet("color: #6a9fb5; letter-spacing: 2px;")
        cl.addWidget(list_label)

        # File List
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget {
                background-color: rgba(5, 15, 25, 180);
                border: 1px solid rgba(100, 180, 255, 25);
                border-radius: 8px; color: #c8e6ff; font-size: 11px; padding: 4px;
            }
            QListWidget::item { padding: 6px 8px; border-bottom: 1px solid rgba(100,180,255,10); }
            QListWidget::item:selected { background-color: rgba(0, 180, 255, 35); color: #fff; }
            QListWidget::item:hover { background-color: rgba(0, 180, 255, 15); }
        """)
        self.file_list.setMaximumHeight(170)
        cl.addWidget(self.file_list)

        # Status
        self.status_label = QLabel("Ready • PDF, DOCX, PY, JS, CSV, JSON, Images, Audio, Video...")
        self.status_label.setWordWrap(True)
        self.status_label.setFont(QFont("Segoe UI", 9))
        self.status_label.setStyleSheet("color: #6a9fb5;")
        cl.addWidget(self.status_label)

        main_layout.addWidget(container)

    def _style_btn(self, btn, bg, hover):
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn.setStyleSheet(f"""
            QPushButton {{ background: {bg}; color: #e0f4ff; border: 1px solid rgba(100,180,255,40);
                border-radius: 6px; padding: 10px; letter-spacing: 1px; }}
            QPushButton:hover {{ background: {hover}; border: 1px solid rgba(100,200,255,80); }}
            QPushButton:pressed {{ background: rgba(0,0,0,100); }}
        """)

    def _browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Files", "", self.SUPPORTED_FORMATS)
        for f in files:
            self._process_and_add(f)

    def _process_and_add(self, filepath):
        from hex_file_upload import hex_file_upload
        result = hex_file_upload.process_file(filepath)
        if result["success"]:
            size_str = result.get("size_str", "")
            ftype = result.get("type", "")
            item = QListWidgetItem(f"✅ {result['name']}  ({size_str}, {ftype})")
            item.setToolTip(result['path'])
            self.file_list.addItem(item)
            self.status_label.setText(f"✅ Uploaded: {result['name']}")
            self.status_label.setStyleSheet("color: #00ff88;")
            self.file_uploaded.emit(filepath)
        else:
            self.status_label.setText(f"❌ {result.get('error', 'Failed')}")
            self.status_label.setStyleSheet("color: #ff4466;")

    def _clear_files(self):
        from hex_file_upload import hex_file_upload
        msg = hex_file_upload.clear_files()
        self.file_list.clear()
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: #ffcc00;")

    # Drag & Drop
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_zone.setStyleSheet("""
                QLabel { background: rgba(0,255,136,25); border: 2px dashed rgba(0,255,136,100);
                    border-radius: 10px; color: #00ff88; padding: 20px; }
            """)
            self.drop_zone.setText("⬇️ Drop Files Here!")

    def dragLeaveEvent(self, event):
        self.drop_zone.setStyleSheet("""
            QLabel { background: rgba(0,180,255,15); border: 2px dashed rgba(100,180,255,50);
                border-radius: 10px; color: #87ceeb; padding: 20px; }
        """)
        self.drop_zone.setText("🎯 Drag & Drop Files Here\nor Click Browse Below")

    def dropEvent(self, event: QDropEvent):
        self.dragLeaveEvent(event)
        for url in event.mimeData().urls():
            fp = url.toLocalFile()
            if os.path.isfile(fp):
                self._process_and_add(fp)

    # Window Drag
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        super().keyPressEvent(event)