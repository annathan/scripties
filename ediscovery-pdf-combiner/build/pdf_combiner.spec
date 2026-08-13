# PyInstaller spec for the eDiscovery PDF Combiner desktop app.
#
# Build locally (on Windows, with requirements.txt + pyinstaller installed):
#   pyinstaller build/pdf_combiner.spec
#
# Produces a single dist/eDiscovery PDF Combiner.exe with no console window.
# Also built automatically by .github/workflows/build-windows-exe.yml.

# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ["../app/gui.py"],
    pathex=["..", "."],
    binaries=[],
    datas=[],
    hiddenimports=[
        "win32com",
        "win32com.client",
        "win32timezone",
        "pywintypes",
        "pythoncom",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="eDiscovery PDF Combiner",
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
    icon=None,
)
