import os
import sys
import shutil
import winreg
import winshell
from win32com.client import Dispatch
from PyQt6.QtWidgets import (QApplication, QWizard, QWizardPage, QVBoxLayout, 
                             QLabel, QCheckBox, QProgressBar, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

APP_NAME = "LensCapture"
DEST_DIR = os.path.join(os.environ["ProgramFiles"], APP_NAME)

class InstallThread(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, run_at_startup):
        super().__init__()
        self.run_at_startup = run_at_startup

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

            # 2. Copy uninstaller
            shutil.copy2(sys.executable, os.path.join(DEST_DIR, "uninstall.exe"))

            # 3. Create Shortcuts
            self.log.emit("Creando accesos directos...")
            shell = Dispatch('WScript.Shell')
            target = os.path.join(DEST_DIR, "LensCapture.exe")
            icon = os.path.join(DEST_DIR, "icon.ico")
            
            # Desktop
            desktop = winshell.desktop()
            path = os.path.join(desktop, "LensCapture.lnk")
            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = target
            shortcut.WorkingDirectory = DEST_DIR
            shortcut.IconLocation = icon
            shortcut.save()
            
            # Start Menu
            start_menu = winshell.programs()
            sm_folder = os.path.join(start_menu, APP_NAME)
            os.makedirs(sm_folder, exist_ok=True)
            
            # App Shortcut
            path = os.path.join(sm_folder, "LensCapture.lnk")
            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = target
            shortcut.WorkingDirectory = DEST_DIR
            shortcut.IconLocation = icon
            shortcut.save()
            
            # Uninstall Shortcut
            path = os.path.join(sm_folder, "Desinstalar LensCapture.lnk")
            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = os.path.join(DEST_DIR, "uninstall.exe")
            shortcut.Arguments = "--uninstall"
            shortcut.WorkingDirectory = DEST_DIR
            shortcut.IconLocation = icon
            shortcut.save()
            
            self.progress.emit(70)

            # 4. Registry entries
            self.log.emit("Configurando registro...")
            
            # Add/Remove Programs
            reg_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{os.path.join(DEST_DIR, "uninstall.exe")}" --uninstall')
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, icon)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Ely")
            winreg.CloseKey(key)
            
            # Run at startup
            if self.run_at_startup:
                run_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(run_key, APP_NAME, 0, winreg.REG_SZ, target)
                winreg.CloseKey(run_key)
                
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
            desktop = winshell.desktop()
            path = os.path.join(desktop, "LensCapture.lnk")
            if os.path.exists(path): os.remove(path)
            
            # Delete Start Menu
            start_menu = winshell.programs()
            sm_folder = os.path.join(start_menu, APP_NAME)
            if os.path.exists(sm_folder): shutil.rmtree(sm_folder)
            
            self.progress.emit(50)
            
            # Delete Registry Add/Remove
            try:
                winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}")
            except: pass
            
            # Delete Startup entry
            try:
                run_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(run_key, APP_NAME)
                winreg.CloseKey(run_key)
            except: pass
            
            self.progress.emit(70)
            
            # To delete the folder, we execute a cmd command that waits 2 seconds and deletes the folder, then exit.
            import subprocess
            cmd = f'ping 127.0.0.1 -n 3 > nul & rmdir /s /q "{DEST_DIR}"'
            subprocess.Popen(cmd, shell=True)
            
            self.progress.emit(100)
            self.log.emit("Desinstalación completada.")
            self.finished.emit(True, "")
            
        except Exception as e:
            self.finished.emit(False, str(e))

class InstallerWizard(QWizard):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Instalador de LensCapture")
        self.setFixedSize(500, 350)
        
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
        page = QWizardPage()
        page.setTitle("Opciones de Configuración")
        layout = QVBoxLayout()
        
        self.cb_startup = QCheckBox("Ejecutar LensCapture al iniciar el sistema (Recomendado)")
        self.cb_startup.setChecked(True)
        layout.addWidget(self.cb_startup)
        
        info = QLabel("<br><br><b>Nota:</b> En el futuro podrás modificar estas opciones y otras "
                      "(como silenciar notificaciones o cambiar de idioma) haciendo "
                      "<b>clic en el botón de Configuración (❓ Ayuda)</b> dentro de la aplicación, "
                      "o buscando LensCapture en tu menú inicio.")
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
        
        self.cb_launch = QCheckBox("Abrir LensCapture ahora")
        self.cb_launch.setChecked(True)
        layout.addWidget(self.cb_launch)
        
        page.setLayout(layout)
        return page

    def on_next(self):
        if self.currentPage() == self.installPage:
            self.button(QWizard.WizardButton.BackButton).setEnabled(False)
            self.button(QWizard.WizardButton.NextButton).setEnabled(False)
            self.button(QWizard.WizardButton.CancelButton).setEnabled(False)
            
            self.thread = InstallThread(self.cb_startup.isChecked())
            self.thread.progress.connect(self.progress.setValue)
            self.thread.log.connect(self.lbl_status.setText)
            self.thread.finished.connect(self.on_install_finished)
            self.thread.start()
            
    def on_install_finished(self, success, error_msg):
        if success:
            self.button(QWizard.WizardButton.NextButton).setEnabled(True)
            self.next()
        else:
            QMessageBox.critical(self, "Error", f"Error durante la instalación:\n{error_msg}")
            self.button(QWizard.WizardButton.CancelButton).setEnabled(True)

    def accept(self):
        if self.cb_launch.isChecked():
            import subprocess
            subprocess.Popen([os.path.join(DEST_DIR, "LensCapture.exe")])
        super().accept()

class UninstallerWizard(QWizard):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Desinstalar LensCapture")
        self.setFixedSize(500, 300)
        
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
            QMessageBox.critical(self, "Error", f"Error durante la desinstalación:\n{error_msg}")
            sys.exit(1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    if "--uninstall" in sys.argv:
        wizard = UninstallerWizard()
    else:
        wizard = InstallerWizard()
        
    wizard.show()
    sys.exit(app.exec())
