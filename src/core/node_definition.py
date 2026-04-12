from __future__ import annotations

from dataclasses import dataclass, field

from core.io_data import IoDataType


@dataclass(frozen=True)
class PortDefinition:
    """Static description of a single input or output port."""
    name: str
    accepted_types: frozenset[IoDataType]

    def __repr__(self) -> str:
        types = ", ".join(t.value for t in self.accepted_types)
        return f"PortDefinition(name={self.name!r}, accepted_types={{{types}}})"


@dataclass
class NodeDefinition:
    """Static description of a node class, produced by the NodeRegistry."""
    class_name: str
    display_name: str
    inputs: list[PortDefinition] = field(default_factory=list)
    outputs: list[PortDefinition] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"NodeDefinition(class_name={self.class_name!r}, "
            f"display_name={self.display_name!r}, "
            f"inputs={self.inputs!r}, "
            f"outputs={self.outputs!r}, "
            f"parameters={self.parameters!r})"
        )
