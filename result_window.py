import json
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel, QPushButton
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QFont, QPixmap

class ResultWindow(QWidget):
    def __init__(self, mode="translation", rect=None, image_path=None):
        super().__init__()
        self.mode = mode
        self.image_path = image_path
        self.pixmap = None
        if image_path:
            self.pixmap = QPixmap(image_path)
            
        if self.mode == "translation" and rect:
            # Frameless overlay mode
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
            self.setGeometry(rect)
            self.json_data = None
        else:
            # Normal window mode
            self.setWindowTitle("Resultados del Análisis")
            self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
            if rect:
                self.setGeometry(rect.x(), rect.y() + rect.height(), 400, 300)
            else:
                self.resize(400, 300)
                
            layout = QVBoxLayout()
            self.loading_label = QLabel("Procesando imagen con IA... Por favor espera.")
            self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.loading_label)
            
            self.text_edit = QTextEdit()
            self.text_edit.setReadOnly(True)
            self.text_edit.hide()
            layout.addWidget(self.text_edit)
            
            self.close_btn = QPushButton("Cerrar")
            self.close_btn.clicked.connect(self.close)
            self.close_btn.hide()
            layout.addWidget(self.close_btn)
            self.setLayout(layout)
            
    def paintEvent(self, event):
        if self.mode != "translation" or not self.pixmap:
            super().paintEvent(event)
            return
            
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.pixmap)
        
        if not self.json_data:
            # Draw a loading indicator on top
            painter.fillRect(self.rect(), QColor(0, 0, 0, 150))
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Traduciendo...")
            return
            
        # Draw translations
        for item in self.json_data:
            try:
                box = item["box"] # [ymin, xmin, ymax, xmax] 0-1000
                translated = item["translated"]
                
                ymin, xmin, ymax, xmax = box
                
                w = self.width()
                h = self.height()
                
                x_px = int((xmin / 1000.0) * w)
                y_px = int((ymin / 1000.0) * h)
                w_px = int(((xmax - xmin) / 1000.0) * w)
                h_px = int(((ymax - ymin) / 1000.0) * h)
                
                line_height = item.get("line_height", ymax - ymin)
                line_h_px = int((line_height / 1000.0) * h)
                
                rect = QRect(x_px, y_px, w_px, h_px)
                
                font = painter.font()
                font.setPixelSize(max(12, int(line_h_px * 0.75)))
                painter.setFont(font)
                
                fm = painter.fontMetrics()
                
                # ── Full-width stripe covers ALL original English text on that row ──
                stripe_rect = QRect(0, y_px, w, h_px)
                painter.fillRect(stripe_rect, QColor(0, 0, 0, 220))

                # Draw translated text left-aligned, starting at the original text's X position
                text_draw_rect = QRect(x_px, y_px, w - x_px - 5, h_px)
                painter.setPen(Qt.GlobalColor.white)
                painter.drawText(text_draw_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, translated)
            except Exception as e:
                import logging
                logging.error(f"Error drawing box: {e}")

    def mousePressEvent(self, event):
        if self.mode == "translation":
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def showEvent(self, event):
        super().showEvent(event)
        self.activateWindow()
        self.raise_()
        self.setFocus()

    def show_result(self, text):
        if self.mode == "translation":
            try:
                import json
                self.json_data = json.loads(text)
            except Exception as e:
                import logging
                logging.error(f"JSON Parse Error: {e}\nRaw Text from Gemini:\n{text}")
                self.json_data = [{"translated": "Error procesando JSON", "box": [0, 0, 1000, 1000]}]
            self.update() # Repaint
        elif self.mode == "ocr":
            self.loading_label.hide()
            self.text_edit.setPlainText(text)
            self.text_edit.show()
            self.close_btn.show()
            
            # Auto copy OCR to clipboard
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            
            self.setWindowTitle("Texto Extraído (Copiado al Portapapeles)")
        else:
            self.loading_label.hide()
            self.text_edit.setPlainText(text)
            self.text_edit.show()
            self.close_btn.show()
        
    def show_error(self, text):
        if self.mode == "translation":
            self.json_data = [{"translated": text, "box": [0, 0, 1000, 1000]}]
            self.update()
        else:
            self.loading_label.hide()
            self.text_edit.setPlainText(text)
            self.text_edit.setStyleSheet("color: red;")
            self.text_edit.show()
            self.close_btn.show()

