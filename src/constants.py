from pathlib import Path

APP_NAME:         str = "Image-Inquest"
APP_DISPLAY_NAME: str = "Sparklehoof"
APP_VERSION:      str = "0.1.0"
API_URL:    str = "https://beltoforion.de"

# Bundled assets (splash image, icons, …)
ASSETS_DIR:        Path = Path(__file__).parent.parent / "assets"
SPLASH_IMAGE_PATH: Path = ASSETS_DIR / "title.png"
SPLASH_DURATION_MS: int = 1800

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
LOG_DIR:  Path = USER_CONFIG_DIR / "logs"
LOG_FILE: Path = LOG_DIR / "image-inquest.log"
