import sys
import threading
import ctypes
import ctypes.wintypes
import logging
import os
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon, QMenu
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QAbstractNativeEventFilter
from PyQt6.QtGui import QIcon, QPixmap, QColor

import config
from main_window import MainWindow
from capture import start_capture_overlay
from result_window import ResultWindow
import gemini_client

log_path = os.path.join(os.environ.get('TEMP', ''), 'lenscapture_debug.log')
logging.basicConfig(filename=log_path, level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

def log_exception(exc_type, exc_value, exc_traceback):
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = log_exception

class Win32HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, eventType, message):
        # In PyQt6, message is a sip.voidptr
        if eventType == b"windows_generic_MSG" or eventType == b"windows_dispatcher_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())
            if msg.message == 0x0312: # WM_HOTKEY
                self.callback()
                # Return True to stop event propagation if needed, but returning False is safer to not break other things
                return False, 0
        return False, 0

class AppController(QObject):
    trigger_capture_signal = pyqtSignal()
    
    VK_MAPPING = {
        "print": 0x2C,
        "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
        "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
        "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B
    }
    
    def __init__(self):
        super().__init__()
        
        # Populate A-Z and 0-9
        for i in range(26):
            self.VK_MAPPING[chr(ord('a') + i)] = 0x41 + i
        for i in range(10):
            self.VK_MAPPING[str(i)] = 0x30 + i
            
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False) # Keep app running in background
        
        self.main_window = MainWindow()
        self.hotkey_id = 1
        self.hotkey_registered = False
        
        # Setup System Tray
        self.tray_icon = QSystemTrayIcon(self)
        
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_path, 'icon.ico')
        self.tray_icon.setIcon(QIcon(icon_path))
        
        tray_menu = QMenu()
        config_action = tray_menu.addAction("Configuración")
        config_action.triggered.connect(self.main_window.show)
        quit_action = tray_menu.addAction("Salir")
        quit_action.triggered.connect(self.quit_app)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        self.tray_icon.showMessage("LensCapture", "Corriendo en segundo plano. Presiona tu atajo para capturar.")
        
        self.trigger_capture_signal.connect(self.do_capture)
        self.current_overlay = None
        self.result_windows = []

        # Setup native Windows hotkey
        self.hotkey_filter = Win32HotkeyFilter(self.on_hotkey)
        self.app.installNativeEventFilter(self.hotkey_filter)
        
        cfg = config.load_config()
        hotkey_str = cfg.get("hotkey", "Print").lower()
        
        modifiers = 0
        if "ctrl" in hotkey_str: modifiers |= 0x0002
        if "shift" in hotkey_str: modifiers |= 0x0004
        if "alt" in hotkey_str: modifiers |= 0x0001
        
        key_part = hotkey_str.split("+")[-1].strip()
        vk = self.VK_MAPPING.get(key_part, 0x2C) # default to print screen
        
        # RegisterHotKey(HWND, id, modifiers, vk)
        user32 = ctypes.windll.user32
        success = user32.RegisterHotKey(None, self.hotkey_id, modifiers, vk)
        if success:
            self.hotkey_registered = True
        else:
            QMessageBox.critical(
                None, 
                "Error de Teclado", 
                f"No se pudo registrar la tecla '{hotkey_str}'.\n"
                "Asegúrate de ejecutar la aplicación como Administrador.\n"
                "O tal vez Lightshot/OneDrive ya está usando esa tecla. Cierra Lightshot y vuelve a intentarlo."
            )

    def on_hotkey(self):
        # This is called from the native event filter
        self.trigger_capture_signal.emit()
        
    def do_capture(self):
        if self.current_overlay is not None:
            return # Already capturing
        
        self.current_overlay = start_capture_overlay(
            self.on_capture_complete,
            self.on_capture_cancelled
        )

    def on_capture_cancelled(self):
        self.current_overlay = None

    def show_notification(self, title, message):
        cfg = config.load_config()
        if not cfg.get("mute_notifications", False):
            self.tray_icon.showMessage(title, message)

    def on_capture_complete(self, payload):
        self.current_overlay = None
        
        parts = payload.split('|')
        image_path = parts[0]
        mode = parts[1] if len(parts) > 1 else "translation"
        
        rect = None
        if len(parts) == 6:
            from PyQt6.QtCore import QRect
            rect = QRect(int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5]))
            
        if mode == "pin":
            import pin_window
            win = pin_window.PinWindow(image_path, int(parts[2]), int(parts[3]))
            self.result_windows.append(win)
            win.show()
            return
            
        if mode == "lens":
            import webbrowser
            import imgur_client
            self.show_notification("Buscando en Lens...", "Subiendo la captura a Google Lens.")
            
            class LensWorker(QThread):
                def run(self):
                    try:
                        url = imgur_client.upload_image(image_path)
                        lens_url = f"https://lens.google.com/uploadbyurl?url={url}"
                        webbrowser.open(lens_url)
                    except Exception as e:
                        print(f"Lens error: {e}")
            self.lens_worker = LensWorker()
            self.lens_worker.start()
            return
        
        if mode == "ocr":
            # Silent OCR - just get text and copy to clipboard
            class OcrWorker(QThread):
                finished = pyqtSignal(str)
                def run(self):
                    import gemini_client
                    import json
                    cfg = config.load_config()
                    try:
                        result = gemini_client.analyze_image(image_path, "ocr", cfg.get("target_language", "Spanish"))
                        self.finished.emit(result)
                    except Exception as e:
                        self.finished.emit("")
            
            self.ocr_worker = OcrWorker()
            def on_ocr_done(text):
                if text:
                    QApplication.clipboard().setText(text)
                    self.show_notification("Texto Copiado", "¡Texto copiado al portapapeles!")
                else:
                    self.show_notification("Error", "No se pudo extraer texto.")
            self.ocr_worker.finished.connect(on_ocr_done)
            self.ocr_worker.start()
            return

        res_win = ResultWindow(mode=mode, rect=rect, image_path=image_path)
        self.result_windows.append(res_win)
        res_win.show()
        
        cfg = config.load_config()
        self.show_notification("Procesando...", "Conectando con Google Lens...")
        
        # Run API call in a separate thread
        class Worker(QThread):
            finished = pyqtSignal(str)
            def run(self):
                import gemini_client
                try:
                    result_text = gemini_client.analyze_image(image_path, mode, cfg.get("target_language", "Spanish"))
                except Exception as e:
                    result_text = f"Error: {e}"
                self.finished.emit(result_text)
                
        self.worker = Worker()
        self.worker.finished.connect(lambda text: res_win.show_result(text))
        self.worker.start()

    def quit_app(self):
        if self.hotkey_registered:
            ctypes.windll.user32.UnregisterHotKey(None, self.hotkey_id)
        self.app.quit()

    def run(self):
        sys.exit(self.app.exec())

if __name__ == "__main__":
    from PyQt6.QtGui import QColor
    controller = AppController()
    controller.run()
