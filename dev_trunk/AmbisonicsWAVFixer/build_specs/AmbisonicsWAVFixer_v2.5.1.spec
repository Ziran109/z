# -*- mode: python ; coding: utf-8 -*-
# AmbisonicsWAVFixer v2.5.1 Build Spec
# 打包成独立无依赖的单文件 EXE

a = Analysis(
    ['../proj_main/AmbisonicsWAVFixer/AmbisonicsWAVFixer.py'],
    pathex=['g:/Coding'],
    binaries=[],
    datas=[],
    hiddenimports=['tkinter', 'tkinter.filedialog', 'tkinter.scrolledtext', 'tkinter.ttk'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'numpy', 'pandas', 'matplotlib', 'scipy', 'pillow'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AmbisonicsWAVFixer_v2.5.1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI mode, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)