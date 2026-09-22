from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, QMessageBox
import config

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Configuración de LensCapture")
        self.resize(350, 220)
        
        self.cfg = config.load_config()
        
        # Set the custom icon
        from PyQt6.QtGui import QIcon
        import os
        import sys
        
        # PyInstaller puts files in sys._MEIPASS when running as EXE
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_path, 'icon.ico')
        self.setWindowIcon(QIcon(icon_path))
        
        central_widget = QWidget()
        layout = QVBoxLayout()

        # Info label (no API key needed)
        info_label = QLabel("✅ Powered by Google Lens — Sin API Key requerida")
        info_label.setStyleSheet("color: #00cc66; font-weight: bold; padding: 4px;")
        layout.addWidget(info_label)
        
        # Mode
        layout.addWidget(QLabel("Modo de Operación:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Traducción Instantánea", "translation")
        self.mode_combo.addItem("Análisis General", "analysis")
        
        idx = self.mode_combo.findData(self.cfg.get("mode", "translation"))
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        layout.addWidget(self.mode_combo)
        
        # Target Language
        layout.addWidget(QLabel("Idioma Destino (para Traducción):"))
        self.lang_combo = QComboBox()
        import gemini_client
        for lang_name in sorted(gemini_client.LANGUAGE_MAP.keys()):
            self.lang_combo.addItem(lang_name)
            
        lang_idx = self.lang_combo.findText(self.cfg.get("target_language", "Spanish"))
        if lang_idx >= 0:
            self.lang_combo.setCurrentIndex(lang_idx)
        layout.addWidget(self.lang_combo)
        
        # Hotkey Info
        layout.addWidget(QLabel("Atajo de teclado (Ej: Ctrl+Shift+X):"))
        from PyQt6.QtWidgets import QKeySequenceEdit, QCheckBox
        from PyQt6.QtGui import QKeySequence
        self.hotkey_input = QKeySequenceEdit()
        self.hotkey_input.setKeySequence(QKeySequence(self.cfg.get("hotkey", "Print")))
        layout.addWidget(self.hotkey_input)
        
        # Mute Notifications
        self.mute_cb = QCheckBox("Silenciar notificaciones")
        self.mute_cb.setChecked(self.cfg.get("mute_notifications", False))
        layout.addWidget(self.mute_cb)
        
        # Run at Startup
        self.startup_cb = QCheckBox("Ejecutar al iniciar Windows (como administrador)")
        self.startup_cb.setChecked(self.cfg.get("run_at_startup", False))
        layout.addWidget(self.startup_cb)

        
        # Info Button
        self.info_btn = QPushButton("❓ Ayuda / Información")
        self.info_btn.clicked.connect(self.show_info)
        layout.addWidget(self.info_btn)

        # Save Button
        self.save_btn = QPushButton("Guardar Configuración y Reiniciar")
        self.save_btn.clicked.connect(self.save_settings)
        layout.addWidget(self.save_btn)
        
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def show_info(self):
        msg = QMessageBox()
        msg.setWindowTitle("Información de LensCapture")
        msg.setText("<b>LensCapture</b> - Herramienta de recortes potenciada por Google Lens.<br><br>"
                    "<b>Controles:</b><br>"
                    "- <b>🖱️ Arrastrar:</b> Selecciona el área a procesar.<br>"
                    "- <b>👆 Seleccionar:</b> Mueve el área seleccionada.<br>"
                    "- <b>Ctrl + S:</b> Guardar imagen.<br>"
                    "- <b>Ctrl + C:</b> Copiar imagen al portapapeles.<br>"
                    "- <b>Ctrl + Shift + C:</b> (OCR) Extraer texto al portapapeles.<br>"
                    "- <b>Herramientas:</b> Lápiz, Líneas, Flechas, Cuadros, Resaltador, Desenfocar.<br>"
                    "- <b>Colores:</b> Haz clic en la paleta para cambiar el color de dibujo.<br>"
                    )
        msg.setIcon(QMessageBox.Icon.Information)
        msg.exec()

    def save_settings(self):
        self.cfg["api_key"] = ""  # No longer needed
        self.cfg["mode"] = self.mode_combo.currentData()
        self.cfg["target_language"] = self.lang_combo.currentText()
        self.cfg["hotkey"] = self.hotkey_input.keySequence().toString()
        self.cfg["mute_notifications"] = self.mute_cb.isChecked()
        self.cfg["run_at_startup"] = self.startup_cb.isChecked()
        
        # Handle auto-start via Scheduled Tasks (Bypasses UAC)
        import subprocess
        import sys
        import winreg
        
        task_name = "LensCapture_AutoStart"
        try:
            if self.cfg["run_at_startup"]:
                cmd = f'schtasks /create /tn "{task_name}" /tr "\\"{sys.executable}\\"" /sc onlogon /rl highest /f'
                subprocess.run(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                cmd = f'schtasks /delete /tn "{task_name}" /f'
                subprocess.run(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            print(f"Error setting scheduled task: {e}")
            
        # Cleanup old registry keys if they exist (from previous versions)
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, "LensCapture")
            winreg.CloseKey(key)
        except: pass
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, "LensCapture")
            winreg.CloseKey(key)
        except: pass

        config.save_config(self.cfg)
        QMessageBox.information(self, "Guardado", "Configuración guardada correctamente.\n\nLa aplicación se reiniciará para aplicar los cambios.")
        import os
        import subprocess
        import sys
        if getattr(sys, 'frozen', False):
            # If compiled with pyinstaller
            subprocess.Popen([sys.executable])
        else:
            subprocess.Popen([sys.executable] + sys.argv)
        sys.exit(0)
