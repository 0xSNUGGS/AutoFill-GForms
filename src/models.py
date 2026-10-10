from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


QUESTION_KINDS = ("single", "multiple", "linear", "grid", "text", "paragraph")


@dataclass(slots=True)
class Question:
    id: str
    number: int
    title: str
    kind: str = "text"
    required: bool = False
    options: list[str] = field(default_factory=list)
    section: str = "General"
    scale_min_label: str = ""
    scale_max_label: str = ""
    rows: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Question":
        return cls(
            id=str(value["id"]),
            number=int(value["number"]),
            title=str(value["title"]),
            kind=str(value.get("kind", "text")),
            required=bool(value.get("required", False)),
            options=[str(option) for option in value.get("options", [])],
            section=str(value.get("section", "General")),
            scale_min_label=str(value.get("scale_min_label", "")),
            scale_max_label=str(value.get("scale_max_label", "")),
            rows=[str(row) for row in value.get("rows", [])],
        )


@dataclass(slots=True)
class ConditionRule:
    id: str
    trigger_question_id: str
    trigger_values: list[str]
    target_question_id: str
    target_config: dict[str, Any]
    match_mode: str = "any"
    action: str = "distribution"
    target_values: list[str] = field(default_factory=list)
    target_section: str = ""
    enabled: bool = True
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ConditionRule":
        return cls(
            id=str(value["id"]),
            trigger_question_id=str(value["trigger_question_id"]),
            trigger_values=[str(item) for item in value.get("trigger_values", [])],
            target_question_id=str(value["target_question_id"]),
            target_config=dict(value.get("target_config", {})),
            match_mode=str(value.get("match_mode", "any")),
            action=str(value.get("action", "distribution")),
            target_values=[str(item) for item in value.get("target_values", [])],
            target_section=str(value.get("target_section", "")),
            enabled=bool(value.get("enabled", True)),
            priority=int(value.get("priority", 0)),
        )
