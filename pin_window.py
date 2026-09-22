from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPixmap

class PinWindow(QWidget):
    def __init__(self, image_path, x, y):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        
        self.image_path = image_path
        pixmap = QPixmap(image_path)
        
        self.setGeometry(x, y, pixmap.width(), pixmap.height())
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.label = QLabel()
        self.label.setPixmap(pixmap)
        layout.addWidget(self.label)
        
        self.setLayout(layout)
        
        self.drag_pos = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.close()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()
