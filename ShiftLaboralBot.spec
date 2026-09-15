# -*- mode: python ; coding: utf-8 -*-
#
# Receta para armar el programa sin ventana de consola detrás. Se construye
# con construir_exe.bat y queda en dist/ShiftLaboralBot/.
#
# Se arma como CARPETA (el .exe con sus archivos al lado) y no como un único
# .exe a propósito: un único .exe tiene que descomprimir todo su contenido en
# %TEMP% cada vez que se abre (incluido el driver de Playwright, ~100 MB), y la
# interfaz lo vuelve a abrir al presionar "Iniciar". Medido el 14/09/2026: la
# ventana tardaba ~18 s en aparecer y el bot ~22 s en arrancar.

import os

import playwright
from PyInstaller.utils.hooks import collect_data_files

# La ruta se calcula acá mismo en vez de dejarla escrita a mano, así esta
# receta sirve igual en cualquier computador.
PLAYWRIGHT_DRIVER = os.path.join(os.path.dirname(playwright.__file__), "driver")

# Cosas que no son código y hay que meter igual: el motor del navegador, los
# temas de la interfaz y el ícono.
datas = [(PLAYWRIGHT_DRIVER, "playwright/driver")]
datas += collect_data_files("customtkinter")
datas += [("icono.ico", ".")]

# Paquetes que PyInstaller arrastra solo porque están instalados en el Python
# del equipo (pandas los menciona como opcionales), pero el bot no usa. Solo
# jedi eran ~5.500 de los ~7.400 archivos del paquete. PIL es opcional en
# customtkinter (solo para CTkImage, que la interfaz no usa).
EXCLUIDOS = [
    "IPython", "ipykernel", "jupyter_client", "jupyter_core", "zmq", "tornado",
    "jedi", "parso", "prompt_toolkit", "pygments", "wcwidth",
    "PIL", "matplotlib", "scipy", "pyarrow", "numba",
    "setuptools", "pkg_resources", "jinja2", "markupsafe", "lxml",
    "pytest", "_pytest",
]


a = Analysis(
    ['app_entry.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUIDOS,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ShiftLaboralBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icono.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ShiftLaboralBot',
)
