import sys
import os
from PyQt6.QtWidgets import QApplication, QWidget, QFileDialog, QTextEdit
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QScreen, QFont, QCursor, QPainterPath
import mss
import mss.tools
from PIL import Image, ImageFilter
import config

class DraggableTextEdit(QTextEdit):
    def __init__(self, parent=None, color=QColor(255, 0, 0)):
        super().__init__(parent)
        self.setStyleSheet(f"background: transparent; color: {color.name()}; border: 1px dashed gray; font-size: 24px; font-family: Arial;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().documentLayout().documentSizeChanged.connect(self.adjust_size)
        self.is_dragging = False
        self.drag_pos = QPoint()

    def adjust_size(self, size):
        self.resize(int(size.width()) + 20, int(size.height()) + 10)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "is_dragging", False):
            self.move(self.mapToParent(event.pos() - self.drag_pos))
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_dragging = False
        super().mouseReleaseEvent(event)

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
        
        self.full_screenshot_path = os.path.join(os.environ.get('TEMP', ''), "temp_full.png")
        self._take_full_screenshot()
        self.bg_pixmap = QPixmap(self.full_screenshot_path)
        
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
                screenshot = sct.grab(monitor)
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=self.full_screenshot_path)
        except Exception as e:
            print(f"Error in take_full_screenshot: {e}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.capture_cancelled.emit()
            self.close()
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

    def _draw_toolbars(self, painter, rect):
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(12)
        painter.setFont(font)
        
        # Calculate horizontal action toolbar total width
        actions = [
            ("💾", QColor(45, 45, 45, 230), "btn_save_rect", 40),
            ("📋", QColor(45, 45, 45, 230), "btn_copy_rect", 40),
            ("📌", QColor(45, 45, 45, 230), "btn_pin_rect", 40),
            ("🔍 Google Lens", QColor(45, 45, 45, 230), "btn_lens_rect", 115),
            ("📄 Texto", QColor(0, 150, 100, 255), "btn_ocr_rect", 70),
            ("✨ Traducir", QColor(0, 150, 100, 255), "btn_translate_rect", 90),
        ]
        
        total_w = sum(w + 5 for _, _, _, w in actions)
        
        # --- Horizontal Action Toolbar (Bottom/Top) ---
        toolbar_y = rect.bottom() + 5
        if toolbar_y + 35 > self.height():
            toolbar_y = rect.top() - 40
            if toolbar_y < 0:
                toolbar_y = 5 # force inside
                
        # If the rect is too far left, move x_offset to the right so buttons are visible
        x_offset = max(rect.right(), total_w + 5)
        if x_offset > self.width():
            x_offset = self.width() - 5
            
        btn_h = 30
        
        for name, color, rect_name, btn_w in reversed(actions):
            x_offset -= (btn_w + 5)
            btn_rect = QRect(x_offset, toolbar_y, btn_w, btn_h)
            setattr(self, rect_name, btn_rect)
            painter.fillRect(btn_rect, color)
            painter.setPen(Qt.GlobalColor.white)
            
            # Use a slightly bigger font for emojis
            font.setPixelSize(14 if len(name) <= 2 else 12)
            painter.setFont(font)
            painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, name)
            
        # --- Vertical Drawing Toolbar (Right/Left) ---
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
            ("🎨", "COLOR", "btn_color_rect"), # We'll handle color specially below
        ]
        
        # 2 columns, 5 rows
        rows = 5
        cols = 2
        
        tools_h = rows * 40
        tools_w = cols * 40
        y_offset_start = max(0, min(rect.top(), self.height() - tools_h))
        
        tools_x_start = rect.right() + 5
        if tools_x_start + tools_w > self.width():
            tools_x_start = rect.left() - tools_w - 5
            if tools_x_start < 0:
                tools_x_start = 5 # force inside
                
        for i, (name, tid, rect_name) in enumerate(tools):
            col = i % cols
            row = i // cols
            
            x_pos = tools_x_start + (col * 40)
            y_pos = y_offset_start + (row * 40)
            
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
                self.active_text_editor = DraggableTextEdit(self, self.current_color)
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
                pen = QPen(self.current_color, 3, Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                r = QRect(self.draw_start_point, pos).normalized()
                painter.drawRect(r)
                painter.end()
            elif self.current_tool == Tool.LINE:
                self.temp_drawing_pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(self.temp_drawing_pixmap)
                pen = QPen(self.current_color, 3, Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                painter.drawLine(self.draw_start_point, pos)
                painter.end()
            elif self.current_tool == Tool.ARROW:
                self.temp_drawing_pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(self.temp_drawing_pixmap)
                pen = QPen(self.current_color, 3, Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                painter.drawLine(self.draw_start_point, pos)
                import math
                angle = math.atan2(pos.y() - self.draw_start_point.y(), pos.x() - self.draw_start_point.x())
                painter.drawLine(pos, QPoint(int(pos.x() - 15 * math.cos(angle - math.pi/6)), int(pos.y() - 15 * math.sin(angle - math.pi/6))))
                painter.drawLine(pos, QPoint(int(pos.x() - 15 * math.cos(angle + math.pi/6)), int(pos.y() - 15 * math.sin(angle + math.pi/6))))
                painter.end()
            elif self.current_tool == Tool.HIGHLIGHT:
                self.temp_drawing_pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(self.temp_drawing_pixmap)
                color = QColor(self.current_color)
                color.setAlpha(100)
                pen = QPen(color, 20, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(self.draw_start_point, pos)
                painter.end()
            elif self.current_tool == Tool.BLUR:
                self.temp_drawing_pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(self.temp_drawing_pixmap)
                painter.fillRect(QRect(self.draw_start_point, pos).normalized(), QColor(0, 0, 0, 150))
                painter.end()
            self.update()

    def _draw_pencil(self, pos):
        painter = QPainter(self.temp_drawing_pixmap)
        pen = QPen(self.current_color, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(self.draw_last_point, pos)
        painter.end()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_selecting:
                self.end_point = event.pos()
                self.is_selecting = False
                rect = self._get_selection_rect()
                if rect.width() > 10 and rect.height() > 10:
                    self.selection_done = True
                    self.set_tool(Tool.SELECT)
                self.update()
                
                # Check for auto_translate after update so it draws the selection before freezing for processing
                if self.selection_done and self.cfg.get("mode", "analysis") == "translation":
                    QApplication.processEvents() # Let the UI paint the selection
                    self._finish_action("translation")
            elif getattr(self, "is_dragging", False):
                self.is_dragging = False
            elif self.is_drawing:
                self.is_drawing = False
                
                if self.current_tool == Tool.BLUR:
                    # Apply actual blur logic using PIL
                    r = QRect(self.draw_start_point, event.pos()).normalized()
                    rect = self._get_selection_rect()
                    # Intersect to avoid blurring outside selection
                    r = r.intersected(rect)
                    if r.width() > 0 and r.height() > 0:
                        # Grab image
                        img_path = self.full_screenshot_path
                        try:
                            pil_img = Image.open(img_path).crop((r.x(), r.y(), r.x()+r.width(), r.y()+r.height()))
                            # Apply strong blur/pixelate
                            pil_img = pil_img.resize((r.width() // 10 or 1, r.height() // 10 or 1), resample=Image.Resampling.BILINEAR)
                            pil_img = pil_img.resize((r.width(), r.height()), Image.Resampling.NEAREST)
                            temp_blur_path = os.path.join(os.environ.get('TEMP', ''), "temp_blur.png")
                            pil_img.save(temp_blur_path)
                            
                            painter = QPainter(self.drawing_pixmap)
                            painter.drawPixmap(r.topLeft(), QPixmap(temp_blur_path))
                            painter.end()
                        except Exception as e:
                            print(f"Blur error: {e}")
                else:
                    painter = QPainter(self.drawing_pixmap)
                    painter.drawPixmap(0, 0, self.temp_drawing_pixmap)
                    painter.end()
                    
                self.temp_drawing_pixmap.fill(Qt.GlobalColor.transparent)
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
                font.setPixelSize(24)
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

