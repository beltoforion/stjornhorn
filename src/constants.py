from pathlib import Path

APP_NAME:    str = "Image-Inquest"
APP_VERSION: str = "0.1.0"
APP_WIDTH:  int = 1024
APP_HEIGHT: int = 768
API_URL:    str = "https://beltoforion.de"

# Built-in nodes shipped with the application
BUILTIN_NODES_DIR: Path = Path(__file__).parent / "nodes"

# Default folders for file dialogs
INPUT_DIR:  Path = Path(__file__).parent.parent / "input"
OUTPUT_DIR: Path = Path(__file__).parent.parent / "output"

# User-defined nodes (~/.image-inquest/user_nodes/)
USER_CONFIG_DIR: Path = Path.home() / ".image-inquest"
USER_NODES_DIR:  Path = USER_CONFIG_DIR / "user_nodes"
