# PyInstaller spec for Stjörnhorn — one-folder bundle.
# Driven by .github/workflows/release.yml on a `v*` tag push. Issue: #157
# pylint: disable=undefined-variable

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Built-in node modules are loaded via importlib at runtime (the registry
# discovers them through an AST scan, then ``importlib.import_module(...)``s
# each one). PyInstaller's static analysis can't see those references, so
# we declare them explicitly. Same story for the ``core`` and ``ui``
# packages, which are wired together through dynamic imports across the
# scene / flow_io layer.
hiddenimports = (
    collect_submodules('nodes')
    + collect_submodules('core')
    + collect_submodules('ui')
    + collect_submodules('ocvl')
)

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        # Read-only bundled resources. The first element is the path on disk
        # (relative to this spec); the second is the destination inside the
        # bundle root that ``sys._MEIPASS`` will point at.
        ('assets/icons',         'assets/icons'),
        ('assets/fonts',         'assets/fonts'),
        ('assets/title.png',     'assets'),
        ('assets/_title.png',    'assets'),
        ('assets/app_icon.ico',  'assets'),
        ('assets/app_icon.png',  'assets'),
        ('doc/welcome.html',     'doc'),
        ('doc/images',           'doc/images'),
        # Built-in node Python sources — the registry AST-parses these to
        # discover node classes, then importlib imports them. Both halves
        # need to be present in the frozen bundle.
        ('src/nodes',            'src/nodes'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='stjornhorn',
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
    icon='assets/app_icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='stjornhorn',
)
