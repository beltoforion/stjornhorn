import ast
from pathlib import Path


class NodeRegistry:
    """Discovers node classes in Python source files via AST scanning.

    The registry maps class names to display names without importing or
    instantiating any node class.  Use it to populate menus or node
    palettes in the UI.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, str] = {}  # class_name -> display_name

    def scan(self, folder: str | Path, skip_files: frozenset[str] = frozenset()) -> None:
        """Scan a folder for node classes and register all discovered nodes.

        Args:
            folder:     Directory to scan for .py files.
            skip_files: File names (not paths) to ignore.
        """
        folder = Path(folder)
        for path in sorted(folder.glob("*.py")):
            if path.name in skip_files:
                continue
            self._nodes.update(_parse_node_file(path))

    @property
    def nodes(self) -> dict[str, str]:
        """Return a {class_name: display_name} snapshot of all registered nodes."""
        return dict(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)

    def __iter__(self):
        return iter(self._nodes.items())


# ── Internal AST helpers ───────────────────────────────────────────────────────

def _parse_node_file(path: Path) -> dict[str, str]:
    """Return {class_name: display_name} for all node classes found in path."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return {}

    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            entry = _extract_node_entry(node)
            if entry is not None:
                class_name, display_name = entry
                result[class_name] = display_name
    return result


def _extract_node_entry(class_node: ast.ClassDef) -> tuple[str, str] | None:
    """Return (class_name, display_name) if the class looks like a node, else None."""
    init = _find_init(class_node)
    if init is None or not _has_super_init(init):
        return None
    if _count_self_calls(init, "_add_input") == 0 and _count_self_calls(init, "_add_output") == 0:
        return None
    display_name = _extract_super_init_name(init) or class_node.name
    return class_node.name, display_name


def _find_init(class_node: ast.ClassDef) -> ast.FunctionDef | None:
    for item in class_node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            return item
    return None


def _has_super_init(init_node: ast.FunctionDef) -> bool:
    for node in ast.walk(init_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "__init__"):
            continue
        if isinstance(func.value, ast.Call) and isinstance(func.value.func, ast.Name) and func.value.func.id == "super":
            return True
    return False


def _extract_super_init_name(init_node: ast.FunctionDef) -> str | None:
    for node in ast.walk(init_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "__init__"):
            continue
        if not (isinstance(func.value, ast.Call) and isinstance(func.value.func, ast.Name) and func.value.func.id == "super"):
            continue
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            return node.args[0].value
    return None


def _count_self_calls(init_node: ast.FunctionDef, method_name: str) -> int:
    count = 0
    for node in ast.walk(init_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == method_name
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
        ):
            count += 1
    return count
