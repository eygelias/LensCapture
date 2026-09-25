import sys
import os
from PyQt6.QtWidgets import QMessageBox,  QApplication, QWidget, QFileDialog, QTextEdit
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QScreen, QFont, QCursor, QPainterPath, QImage
import mss
import mss.tools
from PIL import Image, ImageFilter
import config

class DraggableTextEdit(QTextEdit):
    def __init__(self, parent=None, color=QColor(255, 0, 0), font_size=24):
        super().__init__(parent)
        self.current_color = color
        self.setStyleSheet(f"background: transparent; color: {color.name()}; border: 1px dashed gray; font-size: {font_size}px; font-family: Arial;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().documentLayout().documentSizeChanged.connect(self.adjust_size)
        self.is_dragging = False
        self.drag_pos = QPoint()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        font = self.font()
        size = font.pixelSize()
        if size <= 0: size = 24
        if delta > 0: size += 2
        else: size -= 2
        size = max(8, min(size, 150))
        self.setStyleSheet(f"background: transparent; color: {self.current_color.name()}; border: 1px dashed gray; font-size: {size}px; font-family: Arial;")
        if self.parent() and hasattr(self.parent(), "tool_sizes"):
            self.parent().tool_sizes[self.parent().current_tool] = size
        event.accept()

    def adjust_size(self, size):
        self.resize(int(size.width()) + 20, int(size.height()) + 10)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_pos = event.pos()
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        if hasattr(self, "current_tool") and self.current_tool in self.tool_sizes:
            delta = event.angleDelta().y()
            current_size = self.tool_sizes[self.current_tool]
            
            if delta > 0:
                current_size += max(1, current_size // 10) if self.current_tool == Tool.TEXT else 2
            else:
                current_size -= max(1, current_size // 10) if self.current_tool == Tool.TEXT else 2
                
            min_size = 1
            if self.current_tool == Tool.TEXT: min_size = 8
            if self.current_tool == Tool.HIGHLIGHT: min_size = 5
            
            self.tool_sizes[self.current_tool] = max(min_size, min(current_size, 150))
            
            if self.current_tool == Tool.TEXT and getattr(self, "active_text_editor", None):
                editor = self.active_text_editor
                font = editor.font()
                font.setPixelSize(self.tool_sizes[Tool.TEXT])
                editor.setFont(font)
                editor.setStyleSheet(f"background: transparent; color: {self.current_color.name()}; border: 1px dashed gray; font-size: {self.tool_sizes[Tool.TEXT]}px; font-family: Arial;")
                
            self.update()

    def mouseMoveEvent(self, event):
        if getattr(self, "is_dragging", False):
            self.move(self.mapToParent(event.pos() - self.drag_pos))
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_dragging = False
        super().mouseReleaseEvent(event)
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            # Let the parent handle it to close the text box
            if self.parent():
                self.parent().keyPressEvent(event)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                if hasattr(self.parent(), "_stamp_text_editor"):
                    self.parent()._stamp_text_editor()
        else:
            super().keyPressEvent(event)

class Tool:
    SELECT = 0
    PENCIL = 1
    RECTANGLE = 2
    BLUR = 3
    LINE = 4
    ARROW = 5
    HIGHLIGHT = 6
    TEXT = 7

class OverlayWindow(QWidget):
    capture_complete = pyqtSignal(str) # Emits "path|mode|x|y|w|h"
    capture_cancelled = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.cfg = config.load_config()
        self.auto_translate = self.cfg.get("auto_translate", False)
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        
        self._take_full_screenshot()
        
        self.setGeometry(QApplication.primaryScreen().virtualGeometry())
        
        self.begin_point = QPoint()
        self.end_point = QPoint()
        self.is_selecting = False
        self.selection_done = False
        
        self.drawing_pixmap = QPixmap(self.size())
        self.drawing_pixmap.fill(Qt.GlobalColor.transparent)
        
        self.undo_stack = []
        
        self.current_tool = Tool.SELECT
        self.current_color = QColor(self.cfg.get("drawing_color", "#ff0000"))
        self.tool_sizes = {
            Tool.PENCIL: 3,
            Tool.RECTANGLE: 3,
            Tool.LINE: 3,
            Tool.ARROW: 3,
            Tool.HIGHLIGHT: 20,
            Tool.TEXT: 24
        }
        
        self.is_drawing = False
        self.is_dragging = False
        self.drag_offset = QPoint()
        self.draw_start_point = QPoint()
        self.draw_last_point = QPoint()
        self.temp_drawing_pixmap = QPixmap(self.size())
        self.temp_drawing_pixmap.fill(Qt.GlobalColor.transparent)
        
        # Toolbars
        self.btn_translate_rect = QRect()
        self.btn_ocr_rect = QRect()
        self.btn_lens_rect = QRect()
        self.btn_pin_rect = QRect()
        self.btn_copy_rect = QRect()
        self.btn_save_rect = QRect()
        
        self.btn_select_rect = QRect()
        self.btn_pencil_rect = QRect()
        self.btn_rect_rect = QRect()
        self.btn_blur_rect = QRect()
        self.btn_line_rect = QRect()
        self.btn_arrow_rect = QRect()
        self.btn_highlight_rect = QRect()
        self.btn_text_rect = QRect()
        self.btn_undo_rect = QRect()
        
        self.color_rects = {}
        
    def _take_full_screenshot(self):
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                sct_img = sct.grab(monitor)
                self._bgra_data = sct_img.bgra  # Keep a reference to prevent GC
                img = QImage(self._bgra_data, sct_img.width, sct_img.height, sct_img.width * 4, QImage.Format.Format_ARGB32)
                self.bg_pixmap = QPixmap.fromImage(img)
        except Exception as e:
            import traceback
            err = traceback.format_exc()
            with open(os.path.join(os.environ.get('TEMP', ''), 'lens_capture_error.log'), 'a') as f:
                f.write(err + chr(10))
            QMessageBox.critical(None, "Error de Captura", f"No se pudo tomar la captura de pantalla:\n{e}")
            self.bg_pixmap = QPixmap(QApplication.primaryScreen().virtualGeometry().size())
            self.bg_pixmap.fill(Qt.GlobalColor.black)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if getattr(self, "active_text_editor", None):
                self.active_text_editor.deleteLater()
                self.active_text_editor = None
                self.setFocus()
                if self.undo_stack:
                    self.undo_stack.pop()
            elif self.current_tool != Tool.SELECT:
                self.set_tool(Tool.SELECT)
                self.update()
            else:
                self.capture_cancelled.emit()
                self.close()
        elif event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            if hasattr(self, "current_tool") and self.current_tool in self.tool_sizes:
                current_size = self.tool_sizes[self.current_tool]
                current_size += max(1, current_size // 10) if self.current_tool == Tool.TEXT else 2
                self.tool_sizes[self.current_tool] = min(current_size, 150)
                if self.current_tool == Tool.TEXT and getattr(self, "active_text_editor", None):
                    editor = self.active_text_editor
                    font = editor.font()
                    font.setPixelSize(self.tool_sizes[Tool.TEXT])
                    editor.setFont(font)
                    editor.setStyleSheet(f"background: transparent; color: {self.current_color.name()}; border: 1px dashed gray; font-size: {self.tool_sizes[Tool.TEXT]}px; font-family: Arial;")
                self.update()
        elif event.key() == Qt.Key.Key_Minus:
            if hasattr(self, "current_tool") and self.current_tool in self.tool_sizes:
                current_size = self.tool_sizes[self.current_tool]
                current_size -= max(1, current_size // 10) if self.current_tool == Tool.TEXT else 2
                min_size = 1
                if self.current_tool == Tool.TEXT: min_size = 8
                if self.current_tool == Tool.HIGHLIGHT: min_size = 5
                self.tool_sizes[self.current_tool] = max(min_size, current_size)
                if self.current_tool == Tool.TEXT and getattr(self, "active_text_editor", None):
                    editor = self.active_text_editor
                    font = editor.font()
                    font.setPixelSize(self.tool_sizes[Tool.TEXT])
                    editor.setFont(font)
                    editor.setStyleSheet(f"background: transparent; color: {self.current_color.name()}; border: 1px dashed gray; font-size: {self.tool_sizes[Tool.TEXT]}px; font-family: Arial;")
                self.update()
        elif event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_Z:
                self._undo()
            elif event.key() == Qt.Key.Key_C:
                if self.selection_done:
                    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        self._finish_action("ocr")
                    else:
                        self._copy_to_clipboard()
            elif event.key() == Qt.Key.Key_S:
                if self.selection_done:
                    self._save_to_disk()
            elif event.key() == Qt.Key.Key_T:
                if self.selection_done:
                    self._finish_action("translation")
            elif event.key() == Qt.Key.Key_E:
                if self.selection_done:
                    self._finish_action("ocr")


    def _undo(self):
        if self.undo_stack:
            self.drawing_pixmap = self.undo_stack.pop()
            self.update()

    def _push_undo(self):
        self.undo_stack.append(self.drawing_pixmap.copy())

    def _get_selection_rect(self):
        return QRect(self.begin_point, self.end_point).normalized()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.bg_pixmap)
        
        # Draw drawings directly on top of bg, but only inside the selection if selection is done
        rect = self._get_selection_rect()
        
        if not self.selection_done:
            # Still selecting
            painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
            if self.is_selecting and not rect.isNull():
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                painter.fillRect(rect, Qt.GlobalColor.transparent)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                painter.drawPixmap(rect, self.bg_pixmap, rect)
                pen = QPen(QColor(0, 150, 255), 2, Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                painter.drawRect(rect)
        else:
            # Selection done
            painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
            
            # Draw bg + drawings inside the rect
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            
            # Clip drawing to selection rect
            painter.setClipRect(rect)
            painter.drawPixmap(rect, self.bg_pixmap, rect)
            painter.drawPixmap(rect, self.drawing_pixmap, rect)
            if self.is_drawing:
                painter.drawPixmap(rect, self.temp_drawing_pixmap, rect)
            painter.setClipping(False)
            
            # Draw border
            pen = QPen(QColor(0, 150, 255), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect)
            
            self._draw_toolbars(painter, rect)

    def _draw_pencil(self, pos):
        painter = QPainter(self.drawing_pixmap)
        pen = QPen(self.current_color, self.tool_sizes.get(Tool.PENCIL, 3), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(self.draw_last_point, pos)
        painter.end()

    def _draw_toolbars(self, painter, rect):
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(12)
        painter.setFont(font)
        
        actions = [
            ("💾", QColor(45, 45, 45, 230), "btn_save_rect", 40),
            ("📋", QColor(45, 45, 45, 230), "btn_copy_rect", 40),
            ("📌", QColor(45, 45, 45, 230), "btn_pin_rect", 40),
            ("🔍 Google Lens", QColor(45, 45, 45, 230), "btn_lens_rect", 115),
            ("📄 Texto", QColor(0, 150, 100, 255), "btn_ocr_rect", 70),
            ("✨ Traducir", QColor(0, 150, 100, 255), "btn_translate_rect", 90),
        ]
        total_w = sum(w + 5 for _, _, _, w in actions)
        
        # Determine HT (Horizontal Toolbar) rect
        ht_w = total_w
        ht_h = 35
        ht_y = rect.bottom() + 5
        if ht_y + ht_h > self.height() - 5:
            ht_y = rect.top() - ht_h - 5
            if ht_y < 5:
                ht_y = 5
                
        ht_x = rect.right() - ht_w
        if ht_x < 5:
            ht_x = 5
        if ht_x + ht_w > self.width() - 5:
            ht_x = self.width() - ht_w - 5
            
        ht_rect = QRect(ht_x, ht_y, ht_w, ht_h)
        
        # Determine VT (Vertical Toolbar) rect
        tools = [
            ("👆", Tool.SELECT, "btn_select_rect"),
            ("✏️", Tool.PENCIL, "btn_pencil_rect"),
            ("➖", Tool.LINE, "btn_line_rect"),
            ("↗️", Tool.ARROW, "btn_arrow_rect"),
            ("⬜", Tool.RECTANGLE, "btn_rect_rect"),
            ("🖍️", Tool.HIGHLIGHT, "btn_highlight_rect"),
            ("💧", Tool.BLUR, "btn_blur_rect"),
            ("T", Tool.TEXT, "btn_text_rect"),
            ("↩️", None, "btn_undo_rect"),
            ("🎨", "COLOR", "btn_color_rect"),
        ]
        rows, cols = 5, 2
        vt_w = cols * 40
        vt_h = rows * 40
        
        vt_x = rect.right() + 5
        if vt_x + vt_w > self.width() - 5:
            vt_x = rect.left() - vt_w - 5
            if vt_x < 5:
                vt_x = 5
                
        vt_y = rect.top()
        if vt_y + vt_h > self.height() - 5:
            vt_y = self.height() - vt_h - 5
        if vt_y < 5:
            vt_y = 5
            
        vt_rect = QRect(vt_x, vt_y, vt_w, vt_h)
        
        # Resolve overlap robustly
        if ht_rect.intersects(vt_rect):
            # If they overlap, it's usually because the selection is near the bottom-right.
            # Easiest fix: move VT to the left side of the selection!
            vt_x_alt = rect.left() - vt_w - 5
            if vt_x_alt >= 5:
                vt_rect.moveLeft(vt_x_alt)
            else:
                # If it doesn't fit on the left, push it above HT
                vt_rect.moveTop(ht_rect.top() - vt_h - 5)
                # If it still goes offscreen at top, push HT to the left
                if vt_rect.top() < 5:
                    vt_rect.moveTop(5)
                    ht_rect.moveLeft(vt_rect.left() - ht_w - 5)
                
        # Draw HT
        curr_x = ht_rect.left()
        for name, color, rect_name, btn_w in actions:
            btn_rect = QRect(curr_x, ht_rect.top(), btn_w, 30)
            setattr(self, rect_name, btn_rect)
            painter.fillRect(btn_rect, color)
            painter.setPen(Qt.GlobalColor.white)
            font.setPixelSize(14 if len(name) <= 2 else 12)
            painter.setFont(font)
            painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, name)
            curr_x += btn_w + 5
            
        # Draw VT
        for i, (name, tid, rect_name) in enumerate(tools):
            col = i % cols
            row = i // cols
            x_pos = vt_rect.left() + (col * 40)
            y_pos = vt_rect.top() + (row * 40)
            
            btn_rect = QRect(x_pos, y_pos, 35, 35)
            setattr(self, rect_name, btn_rect)
            
            if tid == "COLOR":
                painter.fillRect(btn_rect, QColor(45, 45, 45, 230))
                inner_rect = btn_rect.adjusted(5, 5, -5, -5)
                painter.fillRect(inner_rect, self.current_color)
                painter.setPen(Qt.GlobalColor.white)
                painter.drawRect(inner_rect)
            else:
                is_active = (self.current_tool == tid and tid is not None)
                color = QColor(0, 150, 255) if is_active else QColor(45, 45, 45, 230)
                
                painter.fillRect(btn_rect, color)
                painter.setPen(Qt.GlobalColor.white)
                
                font.setPixelSize(18)
                painter.setFont(font)
                painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, name)
    def set_tool(self, tool_id):
        self.current_tool = tool_id
        if tool_id == Tool.SELECT:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        elif tool_id == Tool.TEXT:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.capture_cancelled.emit()
            self.close()
            return
            
        if not self.selection_done:
            if event.button() == Qt.MouseButton.LeftButton:
                self.begin_point = event.pos()
                self.end_point = self.begin_point
                self.is_selecting = True
                self.update()
            return
            
        # If selection done, check toolbars first
        pos = event.pos()
            
        if self.btn_translate_rect.contains(pos): self._finish_action("translation"); return
        if self.btn_ocr_rect.contains(pos): self._finish_action("ocr"); return
        if self.btn_lens_rect.contains(pos): self._finish_action("lens"); return
        if self.btn_pin_rect.contains(pos): self._finish_action("pin"); return
        if self.btn_copy_rect.contains(pos): self._copy_to_clipboard(); return
        if self.btn_save_rect.contains(pos): self._save_to_disk(); return
        
        if self.btn_select_rect.contains(pos): self.set_tool(Tool.SELECT); return
        if self.btn_pencil_rect.contains(pos): self.set_tool(Tool.PENCIL); return
        if self.btn_line_rect.contains(pos): self.set_tool(Tool.LINE); return
        if self.btn_arrow_rect.contains(pos): self.set_tool(Tool.ARROW); return
        if self.btn_rect_rect.contains(pos): self.set_tool(Tool.RECTANGLE); return
        if self.btn_highlight_rect.contains(pos): self.set_tool(Tool.HIGHLIGHT); return
        if self.btn_blur_rect.contains(pos): self.set_tool(Tool.BLUR); return
        if self.btn_text_rect.contains(pos):
            self.set_tool(Tool.TEXT)
            # Open input dialog right away or wait for click? Wait for click makes more sense, 
            # but setting the tool is enough for now.
            return
        if self.btn_undo_rect.contains(pos): self._undo(); return
        
        # Check color picker
        if hasattr(self, "btn_color_rect") and self.btn_color_rect.contains(pos):
            from PyQt6.QtWidgets import QColorDialog
            color = QColorDialog.getColor(self.current_color, self, "Seleccionar Color")
            if color.isValid():
                self.current_color = color
                self.cfg["drawing_color"] = color.name()
                config.save_config(self.cfg)
                self.update()
            return
        
        # Check if clicking inside rect to draw or drag
        rect = self._get_selection_rect()
        if rect.contains(pos):
            if self.current_tool == Tool.SELECT:
                self.is_dragging = True
                self.drag_last_pos = pos
                return
            
            if self.current_tool == Tool.TEXT:
                if getattr(self, "active_text_editor", None):
                    # stamp it
                    self._stamp_text_editor()
                
                self._push_undo() # just in case, wait, only push when text is stamped
                self.active_text_editor = DraggableTextEdit(self, self.current_color, self.tool_sizes.get(Tool.TEXT, 24))
                self.active_text_editor.move(pos)
                self.active_text_editor.show()
                self.active_text_editor.setFocus()
                return

            self._push_undo()
            self.is_drawing = True
            self.draw_start_point = pos
            self.draw_last_point = pos
            self.temp_drawing_pixmap.fill(Qt.GlobalColor.transparent)
            
            if self.current_tool == Tool.PENCIL:
                self._draw_pencil(pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_selecting:
                self.end_point = event.pos()
                self.is_selecting = False
                rect = self._get_selection_rect()
                if rect.width() > 5 and rect.height() > 5:
                    self.selection_done = True
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                    if self.cfg.get("mode", "translation") == "translation":
                        self._finish_action("translation")
                        return
                else:
                    # Too small, reset
                    self.begin_point = QPoint()
                    self.end_point = QPoint()
                self.update()
                return

            if getattr(self, "is_dragging", False):
                self.is_dragging = False
                return

            if self.is_drawing:
                pos = event.pos()
                if self.current_tool in (Tool.RECTANGLE, Tool.LINE, Tool.ARROW, Tool.HIGHLIGHT):
                    painter = QPainter(self.drawing_pixmap)
                    painter.drawPixmap(0, 0, self.temp_drawing_pixmap)
                    painter.end()
                    self.temp_drawing_pixmap.fill(Qt.GlobalColor.transparent)
                elif self.current_tool == Tool.BLUR:
                    r = QRect(self.draw_start_point, pos).normalized()
                    rect = self._get_selection_rect()
                    r = r.intersected(rect)
                    if r.width() > 0 and r.height() > 0:
                        try:
                            img = self.bg_pixmap.copy(r).toImage()
                            scaled_down = img.scaled(max(1, r.width() // 10), max(1, r.height() // 10), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                            scaled_up = scaled_down.scaled(r.width(), r.height(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
                            painter = QPainter(self.drawing_pixmap)
                            painter.drawPixmap(r.topLeft(), QPixmap.fromImage(scaled_up))
                            painter.end()
                        except Exception as e:
                            print(f"Blur error: {e}")
                self.is_drawing = False
                self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        from PyQt6.QtWidgets import QToolTip
        tooltip_text = ""
        if hasattr(self, "btn_translate_rect"):
            if self.btn_translate_rect.contains(pos): tooltip_text = "Traducir\nEscanea y traduce el área seleccionada."
            elif self.btn_ocr_rect.contains(pos): tooltip_text = "Extraer Texto (Ctrl+Shift+C)\nCopia el texto al portapapeles."
            elif self.btn_lens_rect.contains(pos): tooltip_text = "Google Lens\nAbre la imagen en Google Lens."
            elif self.btn_copy_rect.contains(pos): tooltip_text = "Copiar Imagen (Ctrl+C)"
            elif self.btn_save_rect.contains(pos): tooltip_text = "Guardar Imagen (Ctrl+S)"
            elif hasattr(self, "btn_select_rect") and self.btn_select_rect.contains(pos): tooltip_text = "Seleccionar/Mover\nPermite mover el área seleccionada."
            elif hasattr(self, "btn_pencil_rect") and self.btn_pencil_rect.contains(pos): tooltip_text = "Lápiz"
            elif hasattr(self, "btn_line_rect") and self.btn_line_rect.contains(pos): tooltip_text = "Línea"
            elif hasattr(self, "btn_arrow_rect") and self.btn_arrow_rect.contains(pos): tooltip_text = "Flecha"
            elif self.btn_rect_rect.contains(pos): tooltip_text = "Rectángulo"
            elif hasattr(self, "btn_highlight_rect") and self.btn_highlight_rect.contains(pos): tooltip_text = "Resaltador"
            elif self.btn_blur_rect.contains(pos): tooltip_text = "Desenfocar"
            elif hasattr(self, "btn_text_rect") and self.btn_text_rect.contains(pos): tooltip_text = "Añadir Texto"
            elif hasattr(self, "btn_undo_rect") and self.btn_undo_rect.contains(pos): tooltip_text = "Deshacer"
            elif hasattr(self, "btn_color_rect") and self.btn_color_rect.contains(pos): tooltip_text = "Color\nCambiar color de dibujo."
            
        in_button = False
        if tooltip_text:
            in_button = True
            QToolTip.showText(event.globalPosition().toPoint(), tooltip_text, self)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            QToolTip.hideText()
            # Restore tool cursor if not in a button
            if self.selection_done:
                if self.current_tool == Tool.SELECT:
                    # SizeAll only if inside rect
                    rect = self._get_selection_rect()
                    if rect.contains(pos):
                        self.setCursor(Qt.CursorShape.SizeAllCursor)
                    else:
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                elif self.current_tool == Tool.TEXT:
                    self.setCursor(Qt.CursorShape.IBeamCursor)
                else:
                    self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)

        if self.is_selecting:
            self.end_point = event.pos()
            self.update()
        elif getattr(self, "is_dragging", False):
            delta = event.pos() - getattr(self, "drag_last_pos", event.pos())
            self.drag_last_pos = event.pos()
            self.begin_point += delta
            self.end_point += delta
            self.update()
        elif self.is_drawing:
            pos = event.pos()
            if self.current_tool == Tool.PENCIL:
                self._draw_pencil(pos)
                self.draw_last_point = pos
            elif self.current_tool == Tool.RECTANGLE:
                self.temp_drawing_pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(self.temp_drawing_pixmap)
                pen = QPen(self.current_color, self.tool_sizes.get(self.current_tool, 3), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                r = QRect(self.draw_start_point, pos).normalized()
                painter.drawRect(r)
                painter.end()
            elif self.current_tool == Tool.LINE:
                self.temp_drawing_pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(self.temp_drawing_pixmap)
                pen = QPen(self.current_color, self.tool_sizes.get(self.current_tool, 3), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.drawLine(self.draw_start_point, pos)
                painter.end()
            elif self.current_tool == Tool.ARROW:
                self.temp_drawing_pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(self.temp_drawing_pixmap)
                pen = QPen(self.current_color, self.tool_sizes.get(self.current_tool, 3), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.drawLine(self.draw_start_point, pos)
                import math
                angle = math.atan2(pos.y() - self.draw_start_point.y(), pos.x() - self.draw_start_point.x())
                arrow_size = max(15, self.tool_sizes.get(Tool.ARROW, 3) * 4)
                painter.drawLine(pos, QPoint(int(pos.x() - arrow_size * math.cos(angle - math.pi/6)), int(pos.y() - arrow_size * math.sin(angle - math.pi/6))))
                painter.drawLine(pos, QPoint(int(pos.x() - arrow_size * math.cos(angle + math.pi/6)), int(pos.y() - arrow_size * math.sin(angle + math.pi/6))))
                painter.end()
            elif self.current_tool == Tool.HIGHLIGHT:
                self.temp_drawing_pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(self.temp_drawing_pixmap)
                color = QColor(self.current_color)
                color.setAlpha(100)
                pen = QPen(color, self.tool_sizes.get(Tool.HIGHLIGHT, 20), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(self.draw_start_point, pos)
                painter.end()
            elif self.current_tool == Tool.BLUR:
                r = QRect(self.draw_start_point, pos).normalized()
                rect = self._get_selection_rect()
                r = r.intersected(rect)
                if r.width() > 0 and r.height() > 0:
                    try:
                        img = self.bg_pixmap.copy(r).toImage()
                        scaled_down = img.scaled(max(1, r.width() // 10), max(1, r.height() // 10), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        scaled_up = scaled_down.scaled(r.width(), r.height(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
                        painter2 = QPainter(self.temp_drawing_pixmap)
                        painter2.drawPixmap(r.topLeft(), QPixmap.fromImage(scaled_up))
                        painter2.end()
                    except Exception as e:
                        print(f"Blur error: {e}")
            self.update()

    def _stamp_text_editor(self):
        if getattr(self, "active_text_editor", None):
            editor = self.active_text_editor
            text = editor.toPlainText()
            if text.strip():
                # self._push_undo() # Already called when text tool clicked, but let's push before stamping
                painter = QPainter(self.drawing_pixmap)
                painter.setPen(QPen(self.current_color))
                font = painter.font()
                font.setPixelSize(self.tool_sizes.get(Tool.TEXT, 24))
                font.setFamily("Arial")
                painter.setFont(font)
                
                # We need to account for widget borders/padding.
                pos = editor.pos()
                painter.drawText(QRect(pos.x(), pos.y(), editor.width(), editor.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, text)
                painter.end()
                
            editor.deleteLater()
            self.active_text_editor = None
            self.update()

    def _composite_image(self):
        self._stamp_text_editor()
        rect = self._get_selection_rect()
        if rect.width() < 10 or rect.height() < 10:
            return None
            
        final_pixmap = QPixmap(rect.size())
        final_pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(final_pixmap)
        painter.drawPixmap(0, 0, self.bg_pixmap, rect.x(), rect.y(), rect.width(), rect.height())
        painter.drawPixmap(0, 0, self.drawing_pixmap, rect.x(), rect.y(), rect.width(), rect.height())
        painter.end()
        
        return final_pixmap

    def _copy_to_clipboard(self):
        pm = self._composite_image()
        if pm:
            QApplication.clipboard().setPixmap(pm)
        self.capture_cancelled.emit()
        self.close()

    def _save_to_disk(self):
        pm = self._composite_image()
        if pm:
            file_path, _ = QFileDialog.getSaveFileName(self, "Guardar Captura", "captura.png", "Images (*.png)")
            if file_path:
                pm.save(file_path)
        self.capture_cancelled.emit()
        self.close()

    def _finish_action(self, mode):
        pm = self._composite_image()
        if not pm:
            self.capture_cancelled.emit()
            return
            
        save_path = os.path.join(os.environ.get('TEMP', ''), f"capture_{mode}.png")
        pm.save(save_path)
        
        rect = self._get_selection_rect()
        self.capture_complete.emit(f"{save_path}|{mode}|{rect.x()}|{rect.y()}|{rect.width()}|{rect.height()}")
        self.close()

def start_capture_overlay(on_capture_complete, on_capture_cancelled):
    overlay = OverlayWindow()
    overlay.capture_complete.connect(on_capture_complete)
    overlay.capture_cancelled.connect(on_capture_cancelled)
    overlay.show()
    overlay.activateWindow()
    overlay.raise_()
    overlay.setFocus()
    return overlay

