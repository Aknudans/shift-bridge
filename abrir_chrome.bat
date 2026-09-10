@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Abrir Chrome de depuracion para el bot ShiftLaboral
echo ============================================================
echo.
echo Esto abre Chrome en el puerto 9222 con un perfil separado
echo (%%LOCALAPPDATA%%\ChromeDebugShiftLaboral). No corre ningun
echo script: sirve para cualquier modo de ejecucion.
echo.
echo   - ejecutar_bot.bat / ejecutar_crear.bat   -> ya abren Chrome solos.
echo   - Comandos "python crear_o_editar.py ..."  con --limpiar-documentos,
echo     --subir-documentos o --no-guardar        -> abrir Chrome con ESTE .bat
echo     primero, iniciar sesion, y despues correr el comando.
echo.

REM Chrome no siempre esta en el mismo lugar: cambia entre la version de 64 y
REM 32 bits y la que se instala solo para un usuario. Se prueban las tres.
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
    echo ERROR: no se encontro chrome.exe en las ubicaciones habituales.
    echo Abrir Chrome manualmente con:
    echo   chrome.exe --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\ChromeDebugShiftLaboral"
    pause
    exit /b 1
)

REM Si ya hay un Chrome con este perfil abierto, esto solo abre una pestaña
REM (no relanza el puerto). Con una vez por sesion alcanza.
start "" "%CHROME%" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\ChromeDebugShiftLaboral" "https://externoslof.shiftlabor.com/"

echo ============================================================
echo   ACCION REQUERIDA:
echo   Si la sesion no estaba iniciada en este perfil, iniciarla
echo   MANUALMENTE en la ventana de Chrome que se abrio.
echo   El bot nunca ve ni guarda la clave.
echo ============================================================
echo.
echo Con la sesion iniciada, ya se puede correr el bot desde otra
echo ventana (esta ventana se puede dejar abierta).
echo.
pause
