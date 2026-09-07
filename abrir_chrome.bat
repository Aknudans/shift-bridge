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
echo     --subir-documentos o --no-guardar        -> abri Chrome con ESTE .bat
echo     primero, inicia sesion, y despues corre el comando.
echo.

REM Si ya hay un Chrome con este perfil abierto, esto solo abre una pestaña
REM (no relanza el puerto). Con una vez por sesion alcanza.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\ChromeDebugShiftLaboral" "https://externoslof.shiftlabor.com/"

echo ============================================================
echo   ACCION REQUERIDA:
echo   Si no habias iniciado sesion en este perfil, hacelo
echo   MANUALMENTE en la ventana de Chrome que se abrio.
echo   El bot nunca ve ni guarda tu clave.
echo ============================================================
echo.
echo Cuando estes con la sesion iniciada, ya podes correr el bot
echo desde otra ventana (deja esta abierta si queres).
echo.
pause
