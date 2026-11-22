# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe: one-folder build (starts faster and uses less RAM than one-file).
from PyInstaller.utils.hooks import collect_data_files

datas = [("inside_voice/locales/*.json", "inside_voice/locales")]
try:
    datas += collect_data_files("_sounddevice_data")  # PortAudio DLL shipped with sounddevice
except Exception:
    pass

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=["pystray._win32", "PIL._tkinter_finder"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "matplotlib", "scipy", "pandas", "IPython", "pytest", "setuptools", "pkg_resources",
        "PyQt5", "PyQt6", "PySide2", "PySide6", "PIL.ImageQt", "numpy.testing",
        "tkinter.test", "test", "distutils",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="InsideVoice",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="InsideVoice",
)
