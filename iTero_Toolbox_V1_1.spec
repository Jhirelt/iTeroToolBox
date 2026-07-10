# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['itero_toolbox.py'],
    pathex=[],
    binaries=[],
    datas=[('itero_toolbox_v1.html', '.'), ('data\\kb_data.json', 'data'), ('Reference', 'Reference')],
    hiddenimports=['webview', 'win32api', 'win32con', 'winreg', 'psutil'],
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
    name='iTero_Toolbox_V1_1',
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
)
