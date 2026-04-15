<p align="center">
  <img src="assets/title.png" alt="Sparklehoof" width="640"/>
</p>

# Sparklehoof

A Python desktop application for building image- and video-processing workflows using a node-based visual editor.

> The repo is still named `image-inquest` while the rebrand to **Sparklehoof** lands piece by piece. `APP_NAME` in `src/constants.py` remains `Image-Inquest` for now so log paths and the user config dir (`~/.image-inquest/`) stay stable.

## Status

Early-stage development. The application provides a two-page UI — a start page and a node editor — with dynamic node creation, linking, flow save/load (`*.flowjs`), and a working **Run** action that executes the active flow. Built-in nodes today: a file source, a grayscale filter, and a file sink.

## Requirements

- Python 3.10+
- [PySide6](https://doc.qt.io/qtforpython-6/)
- NumPy, OpenCV, rawpy

```bash
pip install -r requirements.txt
```

## Running

```bash
python src/main.py
```

Optional arguments:

| Argument | Default | Description |
|---|---|---|
| `--width N` | 1024 | Initial window width in pixels |
| `--height N` | 768 | Initial window height in pixels |
| `--no-splash` | — | Skip the startup splash screen |

## Usage

1. The app opens on the **start page**.
2. Enter a name and click **Create** to open the node editor with a new empty flow, or click **Open** to load an existing `*.flowjs` file.
3. In the editor, drag nodes from the **Palette** dock onto the canvas.
4. Drag between node ports to create links; drag an existing link to remove it.
5. Click **Run** to execute the flow, or **Save** to persist it to `flow/`.

## License

MIT — see [LICENSE](LICENSE).
