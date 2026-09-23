@echo off
echo =========================================
echo Compilando Aplicacion Core LensCapture
echo =========================================
pyinstaller --noconfirm --clean --onedir --windowed --name "LensCapture" --icon "icon.ico" --hidden-import imgur_client --add-data "icon.ico;." app.py
if %ERRORLEVEL% neq 0 (
    echo Error compilando la aplicacion principal.
    pause
    exit /b %ERRORLEVEL%
)

echo =========================================
echo Compilando Instalador de LensCapture
echo =========================================
pyinstaller --noconfirm --clean --onefile --windowed --name "Instalador_LensCapture" --icon "icon.ico" --uac-admin --add-data "icon.ico;." --add-data "dist/LensCapture;LensCapture" installer_wizard.py
if %ERRORLEVEL% neq 0 (
    echo Error compilando el instalador.
    pause
    exit /b %ERRORLEVEL%
)

echo =========================================
echo COMPILACION FINALIZADA EXITOSAMENTE
echo Instalador disponible en la carpeta dist/
echo =========================================
pause
