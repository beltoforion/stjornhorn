from pathlib import Path

APP_NAME:         str = "Image-Inquest"
APP_DISPLAY_NAME: str = "Stjörnhorn"
APP_VERSION:      str = "0.1.26"
API_URL:    str = "https://beltoforion.de"

# Bundled documentation (offline welcome page, screenshots, …)
DOC_DIR:           Path = Path(__file__).parent.parent / "doc"
WELCOME_HTML_PATH: Path = DOC_DIR / "welcome.html"

# Bundled assets (splash image, icons, …)
ASSETS_DIR:        Path = Path(__file__).parent.parent / "assets"
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

# Built-in nodes shipped with the application
BUILTIN_NODES_DIR: Path = Path(__file__).parent / "nodes"

# Default folders for file dialogs
INPUT_DIR:  Path = Path(__file__).parent.parent / "input"
OUTPUT_DIR: Path = Path(__file__).parent.parent / "output"

# Folder where saved flows are written (one JSON file per flow).
FLOW_DIR:   Path = Path(__file__).parent.parent / "flow"

# User-defined nodes (~/.image-inquest/user_nodes/)
USER_CONFIG_DIR: Path = Path.home() / ".image-inquest"
USER_NODES_DIR:  Path = USER_CONFIG_DIR / "user_nodes"

# Logs live next to the application sources rather than in the user
# config dir so they stay visible alongside the rest of the bundled app
# folders (input/, output/, flow/, …).
LOG_DIR:  Path = Path(__file__).parent.parent / "logs"
LOG_FILE: Path = LOG_DIR / "image-inquest.log"
