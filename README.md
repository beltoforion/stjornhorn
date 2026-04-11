# Image Inquest

A Python desktop application for building image processing workflows using a node-based visual editor.

## Status

Early-stage development. The application provides a two-page UI — a start page and a node editor — with dynamic node creation and linking. Actual image processing, flow persistence, and flow loading are not yet implemented.

## Requirements

- Python 3.10+
- [DearPyGUI](https://github.com/hoffstadt/DearPyGui)

```bash
pip install dearpygui
```

## Running

```bash
python src/main.py
```

Optional arguments:

| Argument | Default | Description |
|---|---|---|
| `--width N` | 1024 | Viewport width in pixels |
| `--height N` | 768 | Viewport height in pixels |

## Usage

1. The app opens on the **start page**.
2. Click **New Flow** to create a new empty flow and open the node editor.
3. In the node editor use **Node Editor → Add Node** to add nodes to the canvas.
4. Drag between node attributes to create links; drag an existing link to remove it.
5. Use **Node Editor → Clear All** to remove all nodes, or **Node Editor → Exit** to return to the start page.

## Project Structure

```
src/
├── main.py                 # Entry point and viewport setup
├── constants.py            # Global constants (app name, default size)
├── core/
│   └── flow.py             # Flow domain model (framework-agnostic)
└── ui/
    ├── page.py             # Page abstract base class
    ├── page_manager.py     # Enforces single-active-page invariant
    ├── main_window.py      # Top-level window, menu bar, page wiring
    ├── start_page.py       # Start page (New Flow / Load Flow)
    └── node_editor_page.py # Node editor page
```

## Architecture

The UI is built around a `Page` abstraction. Each page owns a hidden content container and a list of menus it contributes to the viewport menu bar. `PageManager` ensures only one page is active at any time, deactivating the current page before activating the next.

Adding a new page requires only subclassing `Page` and implementing two methods:

```python
class MyPage(Page):
    def _build_ui(self) -> None:
        # create widgets under self._parent, tag the root with self._content_tag, show=False
        ...

    def _install_menus(self) -> None:
        # create menus under self._menu_bar, append their tags to self._menu_tags
        ...
```

The domain layer lives under `src/core/` and has no UI framework dependencies.

## License

MIT — see [LICENSE](LICENSE).
