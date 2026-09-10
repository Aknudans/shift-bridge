# -*- mode: python ; coding: utf-8 -*-
#
# Receta para armar el programa en un solo archivo, sin ventana de consola
# detrás. Se construye con construir_exe.bat y queda en dist/.

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


a = Analysis(
    ['app_entry.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ShiftLaboralBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icono.ico'],
)
