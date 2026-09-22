@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Construir ShiftLaboralBot
echo ============================================================
echo.
echo Esto arma el programa en la carpeta dist\ShiftLaboralBot\ (el .exe
echo con sus archivos al lado). Puede tardar unos minutos (empaqueta el
echo driver de Playwright, ~100 MB).
echo.
echo IMPORTANTE: cerrar el programa si esta abierto antes de construir.
echo.

python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Instalando PyInstaller...
    python -m pip install pyinstaller
)

python -m PyInstaller ShiftLaboralBot.spec --distpath dist --workpath build --noconfirm

rem PyInstaller borra dist\ShiftLaboralBot\ antes de recrearla, asi que estos
rem dos archivos de la entrega hay que volver a copiarlos en cada build. Se
rem perdieron una vez por no hacerlo (22/09/2026): vivian solo ahi y dist\
rem esta en .gitignore.
echo.
echo Copiando los archivos que acompanan al ejecutable...
for %%A in (GUIA_EJECUCION.txt SHIFT_ejemplo.xlsx) do (
    if exist "%%A" (
        copy /y "%%A" "dist\ShiftLaboralBot\" >nul
        echo   - %%A
    ) else (
        echo   ADVERTENCIA: falta %%A en la carpeta del proyecto; no se copio.
    )
)

echo.
if exist "dist\ShiftLaboralBot\ShiftLaboralBot.exe" (
    echo ============================================================
    echo   Listo: dist\ShiftLaboralBot\ShiftLaboralBot.exe
    echo.
    echo   Para entregarlo, copiar la CARPETA completa dist\ShiftLaboralBot\
    echo   ^(o comprimirla en .zip^). El .exe solo, sin su carpeta
    echo   _internal al lado, NO funciona.
    echo ============================================================
) else (
    echo ============================================================
    echo   Algo fallo. Revisar el log de arriba.
    echo ============================================================
)
pause
