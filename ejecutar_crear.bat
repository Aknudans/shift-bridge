@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   Bot ShiftLaboral - Fase 2 (creacion / edicion / documentos)
echo   ATENCION: segun el modo, este script SI modifica datos reales.
echo ============================================================
echo.

REM --- Paso 1: abrir Chrome con el puerto de depuracion, perfil separado ---
REM Se usa un --user-data-dir propio para no chocar con tus ventanas de
REM Chrome normales. La sesion queda guardada entre corridas: solo deberias
REM iniciar sesion la primera vez.
echo [1/4] Abriendo Chrome en modo depuracion (perfil separado)...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\ChromeDebugShiftLaboral" "https://externoslof.shiftlabor.com/"

echo.
echo ============================================================
echo   ACCION REQUERIDA:
echo   Si no habias iniciado sesion en este perfil, hacelo
echo   MANUALMENTE en la ventana de Chrome que se abrio (usuario
echo   y contrasena). El bot nunca ve ni guarda tu clave.
echo   Si ya estabas logueado, solo verifica que la pagina cargo.
echo ============================================================
echo.
pause

REM --- Paso 2: pedir el archivo Excel de entrada ---
echo.
set /p EXCEL_INPUT="[2/4] Arrastra aqui tu archivo Excel de entrada y presiona Enter: "
if "!EXCEL_INPUT!"=="" (
    echo No se indico ningun archivo. Abortando.
    pause
    exit /b 1
)
set EXCEL_INPUT=!EXCEL_INPUT:"=!
if not exist "!EXCEL_INPUT!" (
    echo ERROR: no se encontro el archivo "!EXCEL_INPUT!"
    pause
    exit /b 1
)

REM --- Paso 3: elegir el modo ---
echo.
echo [3/4] Elegi el modo:
echo.
echo   [1] Solo CREAR / EDITAR a las personas (guarda de verdad)
echo   [2] Crear / editar  +  BORRAR los documentos de los que YA existian
echo   [3] Crear / editar  +  BORRAR documentos viejos  +  SUBIR los nuevos
echo   [4] PRUEBA: llena el formulario pero NO guarda ni borra ni sube nada
echo.
set /p MODO="Opcion (1-4): "

set "FLAGS="
if "!MODO!"=="1" set "FLAGS="
if "!MODO!"=="2" set "FLAGS=--limpiar-documentos borrar"
if "!MODO!"=="3" goto pedir_docs
if "!MODO!"=="4" set "FLAGS=--no-guardar"

if not "!MODO!"=="1" if not "!MODO!"=="2" if not "!MODO!"=="3" if not "!MODO!"=="4" (
    echo Opcion invalida. Abortando.
    pause
    exit /b 1
)
goto correr

:pedir_docs
echo.
set /p CARPETA_DOCS="Arrastra la carpeta con las subcarpetas por persona y presiona Enter: "
set CARPETA_DOCS=!CARPETA_DOCS:"=!
if not exist "!CARPETA_DOCS!\" (
    echo ERROR: no se encontro la carpeta "!CARPETA_DOCS!"
    pause
    exit /b 1
)
set "FLAGS=--limpiar-documentos borrar --subir-documentos "!CARPETA_DOCS!""

:correr
echo.
echo [4/4] Ejecutando...  (crear_o_editar.py !FLAGS!)
echo.
python crear_o_editar.py --input "!EXCEL_INPUT!" --output "reporte_crear.xlsx" !FLAGS!

echo.
echo ============================================================
echo   Listo. Revisa reporte_crear.xlsx en esta misma carpeta.
echo ============================================================
pause
