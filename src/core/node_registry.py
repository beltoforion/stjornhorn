import ast
from pathlib import Path

from core.node_definition import NodeDefinition


# Files that are infrastructure, not nodes
PROCESSOR_SKIP_FILES: frozenset[str] = frozenset({"processor_base.py", "io_data.py", "input_output.py"})
SOURCE_SKIP_FILES: frozenset[str] = frozenset({"source_sink.py"})


class NodeRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, NodeDefinition] = {}

    def scan(self, folder: str | Path, skip_files: frozenset[str] = frozenset()) -> None:
        """Scan a folder for node files and register all discovered nodes.

        Args:
            folder: Directory to scan for .py files.
            skip_files: File names (not paths) to ignore, e.g. base-class files.
        """
        folder = Path(folder)
        for path in sorted(folder.glob("*.py")):
            if path.name in skip_files:
                continue
            for definition in _parse_node_file(path):
                self._nodes[definition.class_name] = definition

    @property
    def nodes(self) -> dict[str, NodeDefinition]:
        return dict(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)

    def __iter__(self):
        return iter(self._nodes.values())


# ---------------------------------------------------------------------------
# Internal AST helpers
# ---------------------------------------------------------------------------

def _parse_node_file(path: Path) -> list[NodeDefinition]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    return [
        definition
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        for definition in [_extract_node_definition(node)]
        if definition is not None
    ]


def _extract_node_definition(class_node: ast.ClassDef) -> NodeDefinition | None:
    init_method = _find_init(class_node)
    if init_method is None:
        return None

    # Must have a super().__init__() call — that's how we recognise nodes
    if not _has_super_init(init_method):
        return None

    # Use the string passed to super().__init__("name"), fall back to class name
    display_name = _extract_super_init_name(init_method) or class_node.name

    num_inputs = _count_self_calls(init_method, "_add_input")
    num_outputs = _count_self_calls(init_method, "_add_output")

    # Old-style nodes that never wired up inputs/outputs are skipped
    if num_inputs == 0 and num_outputs == 0:
        return None

    return NodeDefinition(
        class_name=class_node.name,
        display_name=display_name,
        num_inputs=num_inputs,
        num_outputs=num_outputs,
        parameters=_extract_parameters(class_node),
    )


def _find_init(class_node: ast.ClassDef) -> ast.FunctionDef | None:
    for item in class_node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            return item
    return None


def _has_super_init(init_node: ast.FunctionDef) -> bool:
    """Return True if __init__ contains any super().__init__(...) call."""
    for node in ast.walk(init_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "__init__"):
            continue
        receiver = func.value
        if isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name) and receiver.func.id == "super":
            return True
    return False


def _extract_super_init_name(init_node: ast.FunctionDef) -> str | None:
    """Return the first string argument of super().__init__("name"), or None."""
    for node in ast.walk(init_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "__init__"):
            continue
        receiver = func.value
        if not (isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name) and receiver.func.id == "super"):
            continue
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            return node.args[0].value
    return None


def _count_self_calls(init_node: ast.FunctionDef, method_name: str) -> int:
    """Count self.<method_name>(...) calls in __init__."""
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


def _extract_parameters(class_node: ast.ClassDef) -> list[str]:
    """Return names of properties that also have a setter."""
    properties: set[str] = set()
    setters: set[str] = set()

    for item in class_node.body:
        if not isinstance(item, ast.FunctionDef):
            continue
        for decorator in item.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "property":
                properties.add(item.name)
            if (
                isinstance(decorator, ast.Attribute)
                and decorator.attr == "setter"
                and isinstance(decorator.value, ast.Name)
            ):
                setters.add(item.name)

    return sorted(properties & setters)
