import logging
import ast
import sys

from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class ScanError:
    """Describes a problem encountered while scanning a node file."""
    file: Path
    message: str

    def __str__(self) -> str:
        return f"{self.file.name}: {self.message}"


@dataclass
class NodeEntry:
    """Metadata about a discovered node class."""
    class_name:   str   # Python class name, e.g. "FileSource"
    display_name: str   # Human-readable name, e.g. "File Source"
    category:     str   # "Sources" | "Filters" | "Sinks" (from base class)
    section:      str   # Palette section (from the node's own __init__)
    module:       str   # Importable dotted path, e.g. "nodes.sources.file_source"


class NodeRegistry:
    """Discovers node classes in Python source files via AST scanning.

    Each discovered class is stored as a NodeEntry with its display name,
    category and importable module path — without importing or instantiating
    any node.  Use nodes_by_category() to populate a node palette.

    Typical usage at application startup:

        registry = NodeRegistry()
        errors  = registry.scan_builtin(BUILTIN_NODES_DIR)
        errors += registry.scan_user(USER_NODES_DIR)
        if errors:
            # show popup with errors (handled by UI layer)
            ...
    """

    def __init__(self) -> None:
        self._nodes: dict[str, NodeEntry] = {}  # class_name -> NodeEntry

    # ── Scanning ───────────────────────────────────────────────────────────────

    def scan_builtin(self, folder: Path) -> list[ScanError]:
        """Scan the built-in nodes folder recursively.

        The importable module path is computed relative to folder's parent
        (i.e. the src/ directory that is already on sys.path).
        """
        return self._scan(folder, src_root=folder.parent, reject_conflicts=False)

    def scan_user(self, folder: Path) -> list[ScanError]:
        """Scan the user nodes folder recursively, creating it if absent.

        The folder itself is added to sys.path so that user node modules are
        importable.  User node class names must not conflict with already-
        registered built-in nodes — conflicts are rejected and reported.
        """
        _ensure_user_nodes_dir(folder)
        folder_str = str(folder)
        if folder_str not in sys.path:
            sys.path.insert(0, folder_str)
        return self._scan(folder, src_root=folder, reject_conflicts=True)

    def _scan(self, folder: Path, src_root: Path, reject_conflicts: bool) -> list[ScanError]:
        errors: list[ScanError] = []
        
        logger.info(f"Scanning for nodes in {folder} (reject_conflicts={reject_conflicts})")
        
        for path in sorted(folder.rglob("*.py")):
            module = ".".join(path.relative_to(src_root).with_suffix("").parts)
            found, file_errors = _parse_node_file(path)
            errors.extend(file_errors)
            for class_name, display_name, category, section in found:
                logger.info(f"  - {class_name} (display_name={display_name}, category={category}, section={section}, module={module})")

                if reject_conflicts and class_name in self._nodes:
                    errors.append(ScanError(
                        file=path,
                        message=(
                            f"'{class_name}' conflicts with a built-in node "
                            f"and was not loaded"
                        ),
                    ))
                else:
                    self._nodes[class_name] = NodeEntry(
                        class_name=class_name,
                        display_name=display_name,
                        category=category,
                        section=section,
                        module=module,
                    )

        return errors

    # ── Access ─────────────────────────────────────────────────────────────────

    def nodes_by_category(self) -> dict[str, list[NodeEntry]]:
        """Return entries grouped by category, each list sorted by display name."""
        result: dict[str, list[NodeEntry]] = {"Sources": [], "Filters": [], "Sinks": []}
        for entry in self._nodes.values():
            result.setdefault(entry.category, []).append(entry)
        for entries in result.values():
            entries.sort(key=lambda e: e.display_name)
        return result

    def nodes_by_section(self) -> dict[str, list[NodeEntry]]:
        """Return entries grouped by palette section.

        Sections are user-facing labels each node picks in its constructor
        (see :class:`NodeBase.__init__`'s ``section`` parameter). The key
        order reflects the order sections are first seen, so the NodeList
        palette can establish an order without hard-coding section names.
        """
        result: dict[str, list[NodeEntry]] = {}
        for entry in self._nodes.values():
            result.setdefault(entry.section, []).append(entry)
        for entries in result.values():
            entries.sort(key=lambda e: e.display_name)
        return result

    @property
    def nodes(self) -> dict[str, NodeEntry]:
        """Return a snapshot of all registered nodes keyed by class name."""
        return dict(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)

    def __iter__(self):
        return iter(self._nodes.values())


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ensure_user_nodes_dir(folder: Path) -> None:
    """Create the user nodes folder and its subdirectories if they don't exist."""
    for subdir in (folder, folder / "sources", folder / "sinks", folder / "filters"):
        subdir.mkdir(parents=True, exist_ok=True)


# ── AST helpers ────────────────────────────────────────────────────────────────

# Maps base class name → palette category
_CATEGORY_MAP: dict[str, str] = {
    "SourceNodeBase": "Sources",
    "NodeBase":       "Filters",
    "SinkNodeBase":   "Sinks",
}

# Default section used when a node omits ``section=...`` in its
# super().__init__() call. Falls back to the category-derived label so
# legacy / third-party nodes still appear in the palette under a
# sensible heading.
_DEFAULT_SECTION_FOR_CATEGORY: dict[str, str] = {
    "Sources": "Sources",
    "Sinks":   "Sinks",
    "Filters": "Filters",
}


def _parse_node_file(
    path: Path,
) -> tuple[list[tuple[str, str, str, str]], list[ScanError]]:
    """Return ([(class_name, display_name, category, section), ...], [errors]) for a file."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        return [], [ScanError(file=path, message=f"Syntax error: {e.msg} (line {e.lineno})")]
    except OSError as e:
        return [], [ScanError(file=path, message=f"Could not read file: {e}")]

    results: list[tuple[str, str, str, str]] = []
    errors: list[ScanError] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            entry = _extract_node_entry(node)
            if entry is None:
                continue
            validation_errors = _validate_node_class(node, entry[2], path)
            if validation_errors:
                # Reject invalid node classes so they never reach the palette.
                errors.extend(validation_errors)
                continue
            results.append(entry)
    return results, errors


def _extract_node_entry(
    class_node: ast.ClassDef,
) -> tuple[str, str, str, str] | None:
    """Return (class_name, display_name, category, section) if the class is a node, else None."""
    init = _find_init(class_node)
    if init is None or not _has_super_init(init):
        return None
    if _count_self_calls(init, "_add_input") == 0 and _count_self_calls(init, "_add_output") == 0:
        return None
    display_name = _extract_super_init_name(init) or class_node.name
    category = _detect_category(class_node)
    section = (
        _extract_super_init_section(init)
        or _DEFAULT_SECTION_FOR_CATEGORY.get(category, "Filters")
    )
    return class_node.name, display_name, category, section


def _detect_category(class_node: ast.ClassDef) -> str:
    """Infer category from base class names."""
    for base in class_node.bases:
        name: str | None = None
        if isinstance(base, ast.Name):
            name = base.id
        elif isinstance(base, ast.Attribute):
            name = base.attr
        if name and name in _CATEGORY_MAP:
            return _CATEGORY_MAP[name]
    return "Filters"


def _validate_node_class(
    class_node: ast.ClassDef,
    category: str,
    path: Path,
) -> list[ScanError]:
    """Return structural errors for a node class.

    Enforced rules:
      - ``start()`` must not be overridden. It is a final trampoline on
        :class:`SourceNodeBase` that routes through :meth:`process`;
        overriding it would bypass the per-node logging and observer hook
        that the UI relies on to show which node is currently running.
        Non-source classes that define ``start()`` would also silently
        never be called by :meth:`Flow.run`.
    """
    errors: list[ScanError] = []
    if _has_method(class_node, "start"):
        errors.append(ScanError(
            file=path,
            message=(
                f"'{class_node.name}' defines start(), but start() must not "
                f"be overridden. Source nodes should implement process_impl() "
                f"instead; start() is a final trampoline on SourceNodeBase."
            ),
        ))
    return errors


def _has_method(class_node: ast.ClassDef, method_name: str) -> bool:
    for item in class_node.body:
        if isinstance(item, ast.FunctionDef) and item.name == method_name:
            return True
    return False


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


def _extract_super_init_section(init_node: ast.FunctionDef) -> str | None:
    """Return the string value of the ``section`` argument to super().__init__(),
    if any.  Supports both positional (second arg) and keyword form.
    """
    for node in ast.walk(init_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "__init__"):
            continue
        if not (isinstance(func.value, ast.Call) and isinstance(func.value.func, ast.Name) and func.value.func.id == "super"):
            continue
        # Keyword form: super().__init__("Foo", section="Processing")
        for kw in node.keywords:
            if kw.arg == "section" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
        # Positional form: super().__init__("Foo", "Processing")
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
            return node.args[1].value
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
