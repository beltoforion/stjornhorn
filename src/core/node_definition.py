from dataclasses import dataclass, field


@dataclass
class NodeDefinition:
    class_name: str
    display_name: str
    num_inputs: int
    num_outputs: int
    parameters: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"NodeDefinition(class_name={self.class_name!r}, "
            f"display_name={self.display_name!r}, "
            f"num_inputs={self.num_inputs}, "
            f"num_outputs={self.num_outputs}, "
            f"parameters={self.parameters!r})"
        )
