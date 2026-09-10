@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Bot ShiftLaboral - Interfaz grafica
echo ============================================================
echo.
echo Abriendo la interfaz... seleccionar el modo (Comparacion / Creacion /
echo Subir documentos), el Excel y, si corresponde, la carpeta de
echo documentos, desde la ventana que se va a abrir.
echo.

python interfaz.py

if errorlevel 1 (
    echo.
    echo Hubo un error al abrir la interfaz. Verificar que Python y las
    echo dependencias esten instaladas ^(python -m pip install -r requirements.txt^).
    pause
)
