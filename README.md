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

## License

MIT — see [LICENSE](LICENSE).
