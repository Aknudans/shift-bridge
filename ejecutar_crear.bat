@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo   Bot ShiftLaboral - Fase 2 (creacion y edicion)
echo   ATENCION: este script SI modifica datos reales.
echo ============================================================
echo.

REM --- Paso 1: abrir Chrome con el puerto de depuracion, en el mismo perfil ---
REM Se usa el mismo perfil separado que Fase 1 (misma sesion guardada).
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
echo [3/3] Ejecutando creacion/edicion...
echo.
python crear_o_editar.py --input "!EXCEL_INPUT!" --output "reporte_crear.xlsx"

echo.
echo ============================================================
echo   Listo. Revisa reporte_crear.xlsx en esta misma carpeta.
echo ============================================================
pause
