from __future__ import annotations

from typing import Any

from .authorization import validate_form_url
from .models import Question


FORM_TYPE_MAP = {
    0: "text",
    1: "paragraph",
    2: "single",
    4: "multiple",
    5: "linear",
    7: "grid",
}


class FormParsingError(ValueError):
    pass


def _clean(value: object) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").split()).strip()


def _choice_label(choice: list[Any]) -> str:
    label = _clean(choice[0] if choice else "")
    is_other = len(choice) > 4 and choice[4] == 1
    return "Otro:" if is_other and not label else label


def parse_google_form_data(data: list[Any]) -> list[Question]:
    try:
        items = data[1][1]
    except (IndexError, TypeError) as error:
        raise FormParsingError("Google Forms devolvió una estructura desconocida.") from error

    questions: list[Question] = []
    section = "General"
    for item in items:
        if not isinstance(item, list) or len(item) < 5:
            continue
        type_code = item[3]
        if type_code == 8:
            section = _clean(item[1]) or section
            continue
        kind = FORM_TYPE_MAP.get(type_code)
        if kind is None:
            continue
        entries = item[4] or []
        if not entries:
            continue

        options: list[str] = []
        rows: list[str] = []
        scale_min_label = ""
        scale_max_label = ""
        if kind in ("single", "multiple"):
            options = [
                label
                for choice in (entries[0][1] or [])
                if (label := _choice_label(choice))
            ]
        elif kind == "linear":
            options = [_clean(choice[0]) for choice in (entries[0][1] or []) if choice]
            labels = entries[0][3] if len(entries[0]) > 3 else None
            if labels:
                scale_min_label = _clean(labels[0])
                scale_max_label = _clean(labels[-1])
        elif kind == "grid":
            options = [_clean(choice[0]) for choice in (entries[0][1] or []) if choice]
            for entry in entries:
                row_values = entry[3] if len(entry) > 3 else None
                row = _clean(row_values[0]) if row_values else ""
                if row:
                    rows.append(row)

        required = all(bool(entry[2]) for entry in entries if len(entry) > 2)
        questions.append(
            Question(
                id=f"q{len(questions) + 1}",
                number=len(questions) + 1,
                title=_clean(item[1]),
                kind=kind,
                required=required,
                options=options,
                rows=rows,
                section=section,
                scale_min_label=scale_min_label,
                scale_max_label=scale_max_label,
            )
        )
    return questions


def parse_google_form_url(url: str) -> tuple[list[Question], str]:
    public_url = validate_form_url(url)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise FormParsingError("Playwright no está instalado.") from error

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(locale="es-PY")
                page.goto(public_url, wait_until="domcontentloaded", timeout=45_000)
                data = page.evaluate("FB_PUBLIC_LOAD_DATA_")
                public_url = page.url
            finally:
                browser.close()
    except Exception as error:
        raise FormParsingError(f"No se pudo leer la estructura pública del formulario: {error}") from error

    questions = parse_google_form_data(data)
    if not questions:
        raise FormParsingError("No se detectaron preguntas compatibles en el formulario.")
    return questions, public_url
