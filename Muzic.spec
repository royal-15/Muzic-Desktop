# -*- mode: python ; coding: utf-8 -*-

# Release build: PyInstaller creates one windowed executable because this spec
# ends at EXE (there is no COLLECT step). Keep external tools such as FFmpeg
# out of binaries and datas; users configure their own FFmpeg installation.
import sys

from PyInstaller.utils.hooks import collect_all

VERSION = '2.0.1'
PLATFORM_NAMES = {'win32': 'windows', 'linux': 'linux'}
if sys.platform not in PLATFORM_NAMES:
    raise RuntimeError(f'Unsupported build platform: {sys.platform}')
PLATFORM = PLATFORM_NAMES[sys.platform]

yt_dlp_datas, yt_dlp_binaries, yt_dlp_hiddenimports = collect_all('yt_dlp')

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=yt_dlp_binaries,
    # Python source modules are analyzed from run.py imports. Collect yt-dlp's
    # dynamic extractors and package data; FFmpeg remains an external tool.
    datas=yt_dlp_datas,
    hiddenimports=yt_dlp_hiddenimports,
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
    name=f'Muzic-{VERSION}-{PLATFORM}-x64',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
