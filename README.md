# LensCapture

LensCapture es una herramienta de recorte de pantalla y productividad para Windows, construida con Python y PyQt6. Integra funciones de Inteligencia Artificial como traducción instantánea (usando Google Gemini), extracción de texto (OCR), y búsqueda visual en Google Lens.

## 🚀 Características Principales
*   **Captura de Pantalla:** Atajo de teclado global (por defecto Print Screen o la tecla que configures).
*   **Herramientas de Dibujo:** Antes de procesar la imagen, puedes usar el lápiz, resaltador, desenfocar, dibujar flechas, líneas, rectángulos, agregar texto y cambiar colores.
*   **Traducción Instantánea / OCR:** Extrae el texto de la pantalla o tradúcelo a tu idioma usando la IA de Google Gemini. Todo se muestra en una elegante ventana en pantalla con formato Markdown.
*   **Google Lens:** Sube recortes rápidamente para hacer búsqueda visual a través de Google Lens.
*   **Fijar en Pantalla (Pin):** Fija recortes temporales sobre todas tus demás ventanas para tener información a la vista.
*   **Modo Rápido:** Una opción para procesar y traducir el área apenas sueltas el clic del ratón, sin interfaz intermedia.

## 🧠 Arquitectura del Código (Para Agentes de IA)

Si eres un agente de IA y debes modificar, mantener o recrear este código, aquí tienes el contexto técnico de cada módulo:

1.  **pp.py:** El punto de entrada. Maneja la aplicación en el System Tray de Windows (icono al lado del reloj), captura las teclas globales de Windows (usando la librería keyboard con un hook de bajo nivel para saltarse restricciones de Windows) y delega los eventos a los demás módulos.
2.  **capture.py:** El corazón visual. Crea un OverlayWindow translúcido, sin bordes y siempre al frente (Qt.WindowStaysOnTopHint). Se encarga de la captura de pantalla (QScreen), la selección del área, la lógica de dibujo (mousePressEvent, mouseMoveEvent, mouseReleaseEvent) y el dibujado de las barras de herramientas de acciones.
3.  **main_window.py:** La ventana de configuración del programa. Configura atajos de teclado (saltando la interferencia del Snipping Tool usando un botón de reinicio manual), modo de operación, idiomas, y opciones de auto-inicio (usando Tareas Programadas schtasks para evadir el prompt UAC de Windows al inicio).
4.  **config.py:** Lee y escribe la configuración en un archivo JSON local en %APPDATA%\LensCapture.
5.  **gemini_client.py:** Cliente para la API de google-genai. Soporta OCR y Traducción enviando la imagen en Base64 junto a prompts predefinidos.
6.  **imgur_client.py:** Cliente para subir imágenes temporalmente a Imgur. Genera la URL pública que necesita Google Lens para funcionar.
7.  **esult_window.py:** Ventana flotante que muestra los resultados de Gemini. Usa QTextBrowser para soportar renderizado Markdown parcial.
8.  **pin_window.py:** Crea ventanas frameless, siempre visibles (WindowStaysOnTopHint), que muestran imágenes recortadas (QPixmap) y se pueden arrastrar o cerrar.
9.  **installer_wizard.py:** Código del instalador "Custom". Extrae la carpeta dist/LensCapture generada por PyInstaller, la copia a AppData\Local\LensCapture, genera accesos directos (winshell, win32com) en el Menú Inicio y Escritorio, y ejecuta la app de forma silenciosa al finalizar.

## 🛠️ Requisitos de Desarrollo

Instala las dependencias usando el archivo equirements.txt:
\\\ash
pip install -r requirements.txt
\\\

## 📦 Instrucciones para Compilar (PyInstaller)

El programa se compila en 2 fases usando \PyInstaller\. Tienes un script \uild.bat\ para facilitar la tarea. 

### Fase 1: Compilar la Aplicación Core
Genera una carpeta (onedir) con todos los binarios y dependencias.
\\\ash
pyinstaller --noconfirm --clean --onedir --windowed --name "LensCapture" --icon "icon.ico" --hidden-import imgur_client --add-data "icon.ico;." app.py
\\\

### Fase 2: Compilar el Instalador
Toma la carpeta generada en la Fase 1 y la empaqueta dentro de un solo archivo ejecutable (onefile) pidiendo permisos de administrador (\--uac-admin\).
\\\ash
pyinstaller --noconfirm --clean --onefile --windowed --name "Instalador_LensCapture" --icon "icon.ico" --uac-admin --add-data "icon.ico;." --add-data "dist/LensCapture;LensCapture" installer_wizard.py
\\\
El archivo final \Instalador_LensCapture.exe\ quedará en la carpeta \dist/\.
