import ast
from pathlib import Path

from core.node_definition import NodeDefinition


_SKIP_FILES = {"processor_base.py", "io_data.py", "input_output.py"}


class NodeRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, NodeDefinition] = {}

    def scan(self, folder: str | Path) -> None:
        """Scan a folder for processor files and register all discovered nodes."""
        folder = Path(folder)
        for path in sorted(folder.glob("*.py")):
            if path.name in _SKIP_FILES:
                continue
            definitions = _parse_processor_file(path)
            for definition in definitions:
                self._nodes[definition.class_name] = definition

    @property
    def nodes(self) -> dict[str, NodeDefinition]:
        return dict(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)

    def __iter__(self):
        return iter(self._nodes.values())


def _parse_processor_file(path: Path) -> list[NodeDefinition]:
    """Parse a single processor file and return all NodeDefinitions found."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    definitions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            definition = _extract_node_definition(node)
            if definition is not None:
                definitions.append(definition)
    return definitions


def _extract_node_definition(class_node: ast.ClassDef) -> NodeDefinition | None:
    """Extract a NodeDefinition from a class AST node, or None if it is not a processor."""
    init_method = _find_init(class_node)
    if init_method is None:
        return None

    display_name = _extract_display_name(init_method)
    if display_name is None:
        return None

    num_inputs = _count_calls_in_init(init_method, "_add_input")
    num_outputs = _count_calls_in_init(init_method, "_add_output")
    parameters = _extract_parameters(class_node)

    return NodeDefinition(
        class_name=class_node.name,
        display_name=display_name,
        num_inputs=num_inputs,
        num_outputs=num_outputs,
        parameters=parameters,
    )


def _find_init(class_node: ast.ClassDef) -> ast.FunctionDef | None:
    for item in class_node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            return item
    return None


def _extract_display_name(init_node: ast.FunctionDef) -> str | None:
    """
    Extract the display name from a super().__init__("name") call.

    Supports both:
      super().__init__("name")
      super(ClassName, self).__init__("name")
    """
    for node in ast.walk(init_node):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        # Match <anything>.func where func attribute is "__init__"
        if not (isinstance(func, ast.Attribute) and func.attr == "__init__"):
            continue

        # The receiver must be a super() call
        receiver = func.value
        if not (isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name) and receiver.func.id == "super"):
            continue

        # First positional argument must be a string constant
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            return node.args[0].value

    return None


def _count_calls_in_init(init_node: ast.FunctionDef, method_name: str) -> int:
    """Count self.<method_name>(...) calls directly in __init__."""
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
    """Return names of properties that also have a setter defined in the class."""
    properties: set[str] = set()
    setters: set[str] = set()

    for item in class_node.body:
        if not isinstance(item, ast.FunctionDef):
            continue
        for decorator in item.decorator_list:
            # @property
            if isinstance(decorator, ast.Name) and decorator.id == "property":
                properties.add(item.name)
            # @<name>.setter
            if (
                isinstance(decorator, ast.Attribute)
                and decorator.attr == "setter"
                and isinstance(decorator.value, ast.Name)
            ):
                setters.add(item.name)

    return sorted(properties & setters)
