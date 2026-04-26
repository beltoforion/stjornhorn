# PyInstaller spec for Stjörnhorn — one-folder bundle.
# Driven by .github/workflows/release.yml on a `v*` tag push. Issue: #157
# pylint: disable=undefined-variable

import os
import sys

# ``collect_submodules`` resolves a package through the build-time
# interpreter's ``sys.path`` (via ``importlib.util.find_spec``). The
# project uses a ``src/`` layout, so without this insert the ``core`` /
# ``ui`` / ``ocvl`` packages aren't importable from where ``pyinstaller``
# is invoked and ``collect_submodules`` returns nothing. ``pathex``
# below only affects PyInstaller's *Analysis*, not this spec
# interpreter. Issue: #163
_HERE = os.path.dirname(os.path.abspath(SPEC))
_SRC = os.path.join(_HERE, 'src')
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None


def _collect_node_modules() -> list[str]:
    """Enumerate every ``nodes.*`` module under ``src/nodes`` by walking
    the directory tree.

    ``collect_submodules('nodes')`` doesn't pick these up: ``nodes`` and
    its ``filters`` / ``sources`` / ``sinks`` subdirectories are PEP 420
    namespace packages (no ``__init__.py``), and ``pkgutil.iter_modules``
    — which ``collect_submodules`` walks under the hood — silently skips
    namespace-package children of namespace packages. Doing the walk
    ourselves sidesteps that quirk without forcing ``__init__.py`` files
    into the source tree just to satisfy the build tooling.
    """
    nodes_root = os.path.join(_SRC, 'nodes')
    out: list[str] = ['nodes']
    for dirpath, _dirnames, filenames in os.walk(nodes_root):
        rel_dir = os.path.relpath(dirpath, _SRC).replace(os.sep, '.')
        if rel_dir != 'nodes':
            out.append(rel_dir)  # the subpackage itself (nodes.filters, …)
        for f in filenames:
            if not f.endswith('.py') or f == '__init__.py':
                continue
            mod = f'{rel_dir}.{f[:-3]}'
            out.append(mod)
    return out


# Built-in node modules are loaded via importlib at runtime (the registry
# discovers them through an AST scan, then ``importlib.import_module(...)``s
# each one). PyInstaller's static analysis can't see those references, so
# we declare them explicitly. Same story for the ``core`` and ``ui``
# packages, which are wired together through dynamic imports across the
# scene / flow_io layer.
hiddenimports = (
    _collect_node_modules()
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
