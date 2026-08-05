@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   Bot ShiftLaboral - Fase 1 (busqueda y comparacion)
echo ============================================================
echo.

REM --- Paso 1: abrir Chrome con el puerto de depuracion, en un perfil aparte ---
REM Usar un --user-data-dir propio evita el conflicto con tus ventanas de Chrome
REM normales (no hace falta cerrarlas) y hace que la sesion quede guardada entre
REM corridas: solo deberias tener que iniciar sesion la primera vez.
echo [1/3] Abriendo Chrome en modo depuracion (perfil separado)...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\ChromeDebugShiftLaboral" "https://externoslof.shiftlabor.com/"

echo.
echo ============================================================
echo   ACCION REQUERIDA:
echo   Si no habias iniciado sesion antes en este perfil, hazlo
echo   MANUALMENTE en la ventana de Chrome que se abrio (usuario
echo   y contrasena). El bot nunca ve tu clave.
echo   Si ya estabas logueado de una corrida anterior, solo
echo   verifica que la pagina cargo bien y presiona una tecla.
echo ============================================================
echo.
pause

REM --- Paso 2: pedir el archivo Excel de entrada ---
set /p EXCEL_INPUT="[2/3] Arrastra aqui tu archivo Excel de entrada y presiona Enter: "
if "!EXCEL_INPUT!"=="" (
    echo No se indico ningun archivo. Abortando.
    pause
    exit /b 1
)
REM Quita comillas si el arrastre las agrego
set EXCEL_INPUT=!EXCEL_INPUT:"=!

if not exist "!EXCEL_INPUT!" (
    echo ERROR: no se encontro el archivo "!EXCEL_INPUT!"
    pause
    exit /b 1
)

REM --- Paso 3: correr el script ---
echo.
echo [3/3] Ejecutando el bot...
echo.
python buscar_y_comparar.py --input "!EXCEL_INPUT!" --output "reporte.xlsx"

echo.
echo ============================================================
echo   Listo. Revisa reporte.xlsx en esta misma carpeta.
echo ============================================================
pause
