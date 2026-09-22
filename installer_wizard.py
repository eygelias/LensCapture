import os
import sys
import shutil
import winreg
import winshell
from win32com.client import Dispatch
from PyQt6.QtWidgets import (QApplication, QWizard, QWizardPage, QVBoxLayout, 
                             QLabel, QCheckBox, QProgressBar, QMessageBox, QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

APP_NAME = "LensCapture"
DEST_DIR = os.path.join(os.environ["ProgramFiles"], APP_NAME)

class InstallThread(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, run_at_startup, config_data):
        super().__init__()
        self.run_at_startup = run_at_startup
        self.config_data = config_data

    def run(self):
        try:
            # 1. Copy files
            self.log.emit("Preparando instalación...")
            if getattr(sys, 'frozen', False):
                src_dir = os.path.join(sys._MEIPASS, APP_NAME)
            else:
                self.finished.emit(False, "El instalador no está compilado correctamente.")
                return

            self.progress.emit(10)
            
            if not os.path.exists(DEST_DIR):
                os.makedirs(DEST_DIR, exist_ok=True)
                
            self.log.emit("Copiando archivos...")
            total_items = len(os.listdir(src_dir))
            for i, item in enumerate(os.listdir(src_dir)):
                s = os.path.join(src_dir, item)
                d = os.path.join(DEST_DIR, item)
                if os.path.isdir(s):
                    if os.path.exists(d): shutil.rmtree(d)
                    shutil.copytree(s, d)
                else:
                    shutil.copy2(s, d)
                self.progress.emit(10 + int((i / total_items) * 40))

            # Crear config.json
            import json
            config_path = os.path.join(DEST_DIR, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=4)

            # 2. Copy uninstaller
            shutil.copy2(sys.executable, os.path.join(DEST_DIR, "uninstall.exe"))

            # 3. Create Shortcuts
            self.log.emit("Creando accesos directos...")
            shell = Dispatch('WScript.Shell')
            target = os.path.join(DEST_DIR, "LensCapture.exe")
            
            # Desktop
            desktop = winshell.desktop(common=1)
            path = os.path.join(desktop, "LensCapture.lnk")
            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = target
            shortcut.WorkingDirectory = DEST_DIR
            shortcut.IconLocation = target
            shortcut.save()
            
            # Start Menu
            start_menu = winshell.programs(common=1)
            sm_folder = os.path.join(start_menu, APP_NAME)
            os.makedirs(sm_folder, exist_ok=True)
            
            # App Shortcut
            path = os.path.join(sm_folder, "LensCapture.lnk")
            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = target
            shortcut.WorkingDirectory = DEST_DIR
            shortcut.IconLocation = target
            shortcut.save()
            
            # Uninstall Shortcut
            path = os.path.join(sm_folder, "Desinstalar LensCapture.lnk")
            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = os.path.join(DEST_DIR, "uninstall.exe")
            shortcut.Arguments = "--uninstall"
            shortcut.WorkingDirectory = DEST_DIR
            shortcut.IconLocation = os.path.join(DEST_DIR, "uninstall.exe")
            shortcut.save()
            
            self.progress.emit(70)

            # 4. Registry entries
            self.log.emit("Configurando registro...")
            
            # Add/Remove Programs
            reg_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{os.path.join(DEST_DIR, "uninstall.exe")}" --uninstall')
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, target)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Ely")
            winreg.CloseKey(key)
            
            # Run at startup via Scheduled Tasks (Bypasses UAC)
            if self.run_at_startup:
                import subprocess
                task_name = "LensCapture_AutoStart"
                cmd = f'schtasks /create /tn "{task_name}" /tr "\\"{target}\\"" /sc onlogon /rl highest /f'
                subprocess.run(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                
            self.progress.emit(100)
            self.log.emit("¡Instalación completada!")
            self.finished.emit(True, "")

        except Exception as e:
            self.finished.emit(False, str(e))

class UninstallThread(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def run(self):
        try:
            self.log.emit("Eliminando archivos...")
            self.progress.emit(20)
            
            # We can't delete our own executable while running, so we schedule deletion on reboot, 
            # or we rename it and delete the rest.
            
            # Delete Desktop shortcut
            desktop = winshell.desktop(common=1)
            path = os.path.join(desktop, "LensCapture.lnk")
            if os.path.exists(path): os.remove(path)
            
            # Delete Start Menu
            start_menu = winshell.programs(common=1)
            sm_folder = os.path.join(start_menu, APP_NAME)
            if os.path.exists(sm_folder): shutil.rmtree(sm_folder)
            
            self.progress.emit(50)
            
            # Delete Registry Add/Remove
            try:
                winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}")
            except: pass
            
            # Delete Startup entry (Scheduled Task)
            try:
                import subprocess
                task_name = "LensCapture_AutoStart"
                cmd = f'schtasks /delete /tn "{task_name}" /f'
                subprocess.run(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            except: pass
            
            # Cleanup old registry keys if they exist
            try:
                run_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(run_key, APP_NAME)
                winreg.CloseKey(run_key)
            except: pass
            try:
                run_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(run_key, APP_NAME)
                winreg.CloseKey(run_key)
            except: pass
            import subprocess
            cmd = f'ping 127.0.0.1 -n 3 > nul & rmdir /s /q "{DEST_DIR}"'
            subprocess.Popen(cmd, shell=True)
            
            self.progress.emit(100)
            self.log.emit("Desinstalación completada.")
            self.finished.emit(True, "")
            
        except Exception as e:
            self.finished.emit(False, str(e))

DARK_STYLE = """
    QWizard, QWizardPage, QWidget {
        background-color: #2b2b2b;
        color: #ffffff;
    }
    QLabel {
        color: #ffffff;
        background: transparent;
    }
    QFrame[class="OptionBox"] {
        background-color: #333333;
        border: 1px solid #555555;
        border-radius: 6px;
    }
    QFrame[class="OptionBox"]:hover {
        background-color: #404040;
        border: 1px solid #777777;
    }
    QCheckBox {
        color: #ffffff;
        background: transparent;
        font-size: 14px;
    }
    QPushButton {
        background-color: #3b3b3b;
        color: #ffffff;
        border: 1px solid #555555;
        padding: 6px 15px;
        border-radius: 4px;
        min-width: 80px;
    }
    QPushButton:hover {
        background-color: #4b4b4b;
    }
    QPushButton:disabled {
        background-color: #2b2b2b;
        color: #666666;
        border: 1px solid #444444;
    }
    QProgressBar {
        border: 1px solid #555555;
        border-radius: 4px;
        text-align: center;
        background-color: #1e1e1e;
        color: white;
    }
    QProgressBar::chunk {
        background-color: #0078d7;
    }
    QComboBox {
        background-color: #333333;
        color: #ffffff;
        border: 1px solid #555555;
        padding: 8px;
        border-radius: 6px;
    }
    QComboBox:hover {
        background-color: #404040;
        border: 1px solid #777777;
    }
    QComboBox QAbstractItemView {
        background-color: #333333;
        color: #ffffff;
        selection-background-color: #0078d7;
    }
"""

class InstallerWizard(QWizard):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Instalador de LensCapture")
        self.setFixedSize(500, 420)
        self.setStyleSheet(DARK_STYLE)
        
        # Ocultar la barra gris claro por defecto de QWizard en Windows
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        
        self.addPage(self.createWelcomePage())
        self.addPage(self.createOptionsPage())
        self.installPage = self.createInstallPage()
        self.addPage(self.installPage)
        self.addPage(self.createFinishPage())
        
        self.button(QWizard.WizardButton.NextButton).clicked.connect(self.on_next)

    def createWelcomePage(self):
        page = QWizardPage()
        page.setTitle("Bienvenido al Instalador de LensCapture")
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Este asistente instalará <b>LensCapture</b> en tu equipo.<br><br>"
                                "LensCapture es una herramienta potenciada por Google Lens para traducir, copiar texto (OCR) y capturar tu pantalla.<br><br>"
                                "Haz clic en Siguiente para continuar."))
        page.setLayout(layout)
        return page

    def createOptionsPage(self):
        from PyQt6.QtWidgets import QComboBox
        page = QWizardPage()
        page.setTitle("Opciones de Configuración")
        layout = QVBoxLayout()
        
        # Opcion de inicio
        frame1 = QFrame()
        frame1.setProperty("class", "OptionBox")
        lyt1 = QVBoxLayout(frame1)
        self.cb_startup = QCheckBox("Ejecutar LensCapture al iniciar Windows (Recomendado)")
        self.cb_startup.setChecked(True)
        lyt1.addWidget(self.cb_startup)
        layout.addWidget(frame1)
        
        # Opcion de notificaciones
        frame2 = QFrame()
        frame2.setProperty("class", "OptionBox")
        lyt2 = QVBoxLayout(frame2)
        self.cb_mute = QCheckBox("Silenciar notificaciones (No mostrar mensajes emergentes)")
        self.cb_mute.setChecked(False)
        lyt2.addWidget(self.cb_mute)
        layout.addWidget(frame2)
        
        # Opcion de idioma
        layout.addWidget(QLabel("<br><b>Idioma destino para las traducciones:</b>"))
        self.combo_lang = QComboBox()
        self.combo_lang.addItems([
            "Spanish", "English", "French", "German", "Italian",
            "Portuguese", "Russian", "Japanese", "Korean", "Chinese"
        ])
        layout.addWidget(self.combo_lang)
        
        info = QLabel("<br><b>Nota:</b> En el futuro podrás modificar estas opciones haciendo "
                      "<b>clic en el botón de Configuración (❓ Ayuda)</b> en el menú de la aplicación.")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        page.setLayout(layout)
        return page

    def createInstallPage(self):
        page = QWizardPage()
        page.setTitle("Instalando...")
        layout = QVBoxLayout()
        
        self.lbl_status = QLabel("Preparando...")
        layout.addWidget(self.lbl_status)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        
        page.setLayout(layout)
        return page

    def createFinishPage(self):
        page = QWizardPage()
        page.setTitle("Instalación Completada")
        layout = QVBoxLayout()
        layout.addWidget(QLabel("LensCapture se ha instalado correctamente en tu equipo."))
        
        frame = QFrame()
        frame.setProperty("class", "OptionBox")
        lyt = QVBoxLayout(frame)
        self.cb_launch = QCheckBox("Abrir LensCapture ahora")
        self.cb_launch.setChecked(True)
        lyt.addWidget(self.cb_launch)
        layout.addWidget(frame)
        
        page.setLayout(layout)
        return page

    def on_next(self):
        if self.currentPage() == self.installPage:
            self.button(QWizard.WizardButton.BackButton).setEnabled(False)
            self.button(QWizard.WizardButton.NextButton).setEnabled(False)
            self.button(QWizard.WizardButton.CancelButton).setEnabled(False)
            
            # Recopilar configuracion
            config_data = {
                "mode": "analysis",
                "target_language": self.combo_lang.currentText(),
                "hotkey": "print screen",
                "drawing_color": "#ff0000",
                "mute_notifications": self.cb_mute.isChecked(),
                "run_at_startup": self.cb_startup.isChecked()
            }
            
            self.thread = InstallThread(self.cb_startup.isChecked(), config_data)
            self.thread.progress.connect(self.progress.setValue)
            self.thread.log.connect(self.lbl_status.setText)
            self.thread.finished.connect(self.on_install_finished)
            self.thread.start()
            
    def on_install_finished(self, success, error_msg):
        if success:
            self.button(QWizard.WizardButton.NextButton).setEnabled(True)
            self.next()
        else:
            QMessageBox.critical(self, "Error", f"Error durante la instalación:\\n{error_msg}")
            self.button(QWizard.WizardButton.CancelButton).setEnabled(True)

    def accept(self):
        if self.cb_launch.isChecked():
            import subprocess
            subprocess.Popen([os.path.join(DEST_DIR, "LensCapture.exe")], cwd=DEST_DIR)
        super().accept()

class UninstallerWizard(QWizard):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Desinstalar LensCapture")
        self.setFixedSize(500, 300)
        self.setStyleSheet(DARK_STYLE)
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        
        page = QWizardPage()
        page.setTitle("Desinstalando...")
        layout = QVBoxLayout()
        
        self.lbl_status = QLabel("Iniciando desinstalación...")
        layout.addWidget(self.lbl_status)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        
        page.setLayout(layout)
        self.addPage(page)
        
        self.button(QWizard.WizardButton.BackButton).hide()
        self.button(QWizard.WizardButton.NextButton).hide()
        self.button(QWizard.WizardButton.CancelButton).setEnabled(False)
        
        self.thread = UninstallThread()
        self.thread.progress.connect(self.progress.setValue)
        self.thread.log.connect(self.lbl_status.setText)
        self.thread.finished.connect(self.on_uninstall_finished)
        self.thread.start()
        
    def on_uninstall_finished(self, success, error_msg):
        if success:
            QMessageBox.information(self, "Desinstalación Completada", "LensCapture fue eliminado de su equipo.")
            sys.exit(0)
        else:
            QMessageBox.critical(self, "Error", f"Error durante la desinstalación:\\n{error_msg}")
            sys.exit(1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # FORZAR ESTILO FUSION (SOLUCIONA EL MODO OSCURO)
    app.setStyle("Fusion")
    
    if "--uninstall" in sys.argv:
        wizard = UninstallerWizard()
    else:
        wizard = InstallerWizard()
        
    wizard.show()
    sys.exit(app.exec())
