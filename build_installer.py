import os
import sys
import shutil
import winshell
from win32com.client import Dispatch

def install():
    print("Instalando LensCapture...")
    
    # Destination
    dest_dir = os.path.join(os.environ["ProgramFiles"], "LensCapture")
    
    # Source
    if getattr(sys, 'frozen', False):
        src_dir = os.path.join(sys._MEIPASS, "LensCapture")
    else:
        print("Debe ejecutarse como binario compilado.")
        return
        
    # Create dest
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir, exist_ok=True)
        
    # Copy files
    print(f"Copiando archivos a {dest_dir}...")
    for item in os.listdir(src_dir):
        s = os.path.join(src_dir, item)
        d = os.path.join(dest_dir, item)
        if os.path.isdir(s):
            if os.path.exists(d):
                shutil.rmtree(d)
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
            
    # Create Desktop Shortcut
    desktop = winshell.desktop()
    path = os.path.join(desktop, "LensCapture.lnk")
    target = os.path.join(dest_dir, "LensCapture.exe")
    icon = os.path.join(dest_dir, "icon.ico")
    
    print("Creando acceso directo...")
    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(path)
    shortcut.Targetpath = target
    shortcut.WorkingDirectory = dest_dir
    shortcut.IconLocation = icon
    shortcut.save()
    
    # Create Start Menu Shortcut
    start_menu = winshell.programs()
    path = os.path.join(start_menu, "LensCapture.lnk")
    shortcut = shell.CreateShortCut(path)
    shortcut.Targetpath = target
    shortcut.WorkingDirectory = dest_dir
    shortcut.IconLocation = icon
    shortcut.save()
    
    import ctypes
    ctypes.windll.user32.MessageBoxW(0, "¡LensCapture se ha instalado correctamente!\n\nPuedes abrirlo desde el acceso directo en tu escritorio.", "Instalación Exitosa", 64)

if __name__ == "__main__":
    try:
        install()
    except Exception as e:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, f"Error durante la instalación:\n{str(e)}", "Error", 16)
