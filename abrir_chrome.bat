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

REM Si ya hay un Chrome con este perfil abierto, esto solo abre una pestaña
REM (no relanza el puerto). Con una vez por sesion alcanza.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\ChromeDebugShiftLaboral" "https://externoslof.shiftlabor.com/"

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
