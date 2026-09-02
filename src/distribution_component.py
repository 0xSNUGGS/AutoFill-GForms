from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st


_ASSET_PATH = Path(__file__).resolve().parents[1] / "components" / "distribution_editor"
_distribution_editor = None


def register_distribution_component() -> None:
    """Register the v2 component in each Streamlit script execution."""

    global _distribution_editor
    _distribution_editor = st.components.v2.component(
        "forms_distribution_editor",
        html=(_ASSET_PATH / "component.html").read_text(encoding="utf-8"),
        css=(_ASSET_PATH / "component.css").read_text(encoding="utf-8"),
        js=(_ASSET_PATH / "component.js").read_text(encoding="utf-8"),
    )


def distribution_editor(
    *,
    kind: str,
    options: list[dict[str, str]],
    counts: dict[str, int],
    total: int,
    input_mode: str,
    minimum: int = 0,
    maximum: int | None = None,
    key: str,
) -> dict[str, Any] | None:
    """Render an integer-based graphical distribution editor."""

    if _distribution_editor is None:
        register_distribution_component()
    default = {"counts": counts, "inputMode": input_mode}
    result = _distribution_editor(
        data={
            "kind": kind,
            "options": options,
            "counts": counts,
            "total": total,
            "inputMode": input_mode,
            "minimum": minimum,
            "maximum": maximum if maximum is not None else len(options),
        },
        default={"value": default},
        on_value_change=lambda: None,
        key=key,
        width="stretch",
        height="content",
    )
    value = getattr(result, "value", None)
    return value if isinstance(value, dict) else None
