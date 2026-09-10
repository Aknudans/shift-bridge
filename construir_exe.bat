@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Construir ShiftLaboralBot.exe
echo ============================================================
echo.
echo Esto arma el ejecutable en dist\ShiftLaboralBot.exe. Puede tardar
echo unos minutos (empaqueta el driver de Playwright, ~100 MB).
echo.

python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Instalando PyInstaller...
    python -m pip install pyinstaller
)

python -m PyInstaller ShiftLaboralBot.spec --distpath dist --workpath build

echo.
if exist "dist\ShiftLaboralBot.exe" (
    echo ============================================================
    echo   Listo: dist\ShiftLaboralBot.exe
    echo ============================================================
) else (
    echo ============================================================
    echo   Algo fallo. Revisar el log de arriba.
    echo ============================================================
)
pause
