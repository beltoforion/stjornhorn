import os
import sys
from pathlib import Path

APP_NAME:         str = "Image-Inquest"
APP_DISPLAY_NAME: str = "Stjörnhorn"
APP_VERSION:      str = "0.2.2"
API_URL:    str = "https://beltoforion.de"

# Path resolution -----------------------------------------------------------
#
# In dev mode, resources sit next to the source tree (assets/, doc/, flow/
# alongside src/). When packaged with PyInstaller, data files declared in
# ``stjornhorn.spec`` are extracted under ``sys._MEIPASS`` at startup, and
# that root is read-only — anything the app needs to write (saved flows,
# logs, default input/output dirs) must live in a per-user directory
# instead. Issue: #157
_FROZEN: bool = bool(getattr(sys, "frozen", False))


def _resource_root() -> Path:
    """Root for read-only bundled data (assets, doc, built-in node sources)."""
    if _FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent.parent


def _user_data_root() -> Path:
    """Per-user writable area for flows, logs, default input/output dirs."""
    if not _FROZEN:
        return Path(__file__).parent.parent
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Stjornhorn"
    return Path.home() / ".local" / "share" / "Stjornhorn"


_RES = _resource_root()
_USR = _user_data_root()

# Bundled documentation (offline welcome page, screenshots, …)
DOC_DIR:           Path = _RES / "doc"
WELCOME_HTML_PATH: Path = DOC_DIR / "welcome.html"

# Bundled assets (splash image, icons, …)
ASSETS_DIR:        Path = _RES / "assets"
SPLASH_IMAGE_PATH: Path = ASSETS_DIR / "title.png"
SPLASH_DURATION_MS: int = 1800

# Application window / taskbar icon. Prefer the .ico (multi-resolution,
# correct on Windows title bars and taskbar) with the .png as a fallback
# for platforms or toolchains that don't pick up ICO.
APP_ICON_PATH:          Path = ASSETS_DIR / "app_icon.ico"
APP_ICON_FALLBACK_PATH: Path = ASSETS_DIR / "app_icon.png"

# Windows groups taskbar entries by AppUserModelID and uses it to find
# the right icon. Without this, Python-hosted apps inherit the generic
# python.exe icon in the taskbar.
APP_USER_MODEL_ID: str = "Beltoforion.Sparklehoof.ImageInquest.0.1.1"

# Google Material Icons font, rendered into QIcons by ``ui.icons``.
MATERIAL_ICONS_FONT_PATH: Path = ASSETS_DIR / "fonts" / "MaterialIcons-Regular.ttf"

# Built-in nodes shipped with the application. The registry AST-scans the
# .py sources, so in a frozen bundle we need the source tree itself —
# bundled under ``src/nodes`` via the spec's ``datas=``. In dev mode the
# scan reads directly from the working tree.
BUILTIN_NODES_DIR: Path = (_RES / "src" / "nodes") if _FROZEN else (Path(__file__).parent / "nodes")

# Default folders for file dialogs
INPUT_DIR:  Path = _USR / "input"
OUTPUT_DIR: Path = _USR / "output"

# Folder where saved flows are written (one JSON file per flow).
FLOW_DIR:   Path = _USR / "flow"

# User-defined nodes (~/.image-inquest/user_nodes/)
USER_CONFIG_DIR: Path = Path.home() / ".image-inquest"
USER_NODES_DIR:  Path = USER_CONFIG_DIR / "user_nodes"

# Logs. In dev mode they sit next to the app sources; in a frozen bundle
# they live under the per-user data dir alongside flow/, input/, output/.
LOG_DIR:  Path = _USR / "logs"
LOG_FILE: Path = LOG_DIR / "image-inquest.log"
