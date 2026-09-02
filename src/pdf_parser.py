from __future__ import annotations

import io
import re
from typing import BinaryIO

import pdfplumber

from .models import Question


QUESTION_RE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")
SECONDARY_NUMBER_RE = re.compile(r"^\d+\.\s+")
SECTION_RE = re.compile(r"^Secci[oó]n\s+", re.IGNORECASE)
SCALE_RE = re.compile(r"^(?:\d+\s+){2,}\d+$")
PAGE_RE = re.compile(r"^\d+\s*/\s*\d+$")
DATE_HEADER_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}")


IGNORED_PREFIXES = (
    "* Indica que la pregunta es obligatoria",
    "Este contenido no ha sido creado",
    "https://docs.google.com/forms/",
)


def _clean(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split()).strip()


def _is_noise(line: str) -> bool:
    return (
        not line
        or PAGE_RE.fullmatch(line) is not None
        or DATE_HEADER_RE.match(line) is not None
        or line == "Formularios"
        or any(line.startswith(prefix) for prefix in IGNORED_PREFIXES)
    )


def _strip_branch(value: str) -> str:
    return re.split(r"\s+Salta a la pregunta\s+\d+", value, maxsplit=1)[0].strip()


def _finalize(raw: dict | None, questions: list[Question]) -> None:
    if raw is None:
        return
    title = _clean(" ".join(raw["title_parts"]))
    title = _clean(title.replace(" * ", " ").removesuffix("*"))
    if not title:
        return
    options: list[str] = []
    for option in raw["options"]:
        option = _strip_branch(_clean(option)).removesuffix("*").strip()
        if option and option not in options:
            options.append(option)
    kind = raw["kind"]
    if kind == "unknown":
        kind = "paragraph" if "(Opcional)" in title else "text"
    if kind in ("single", "multiple") and SCALE_RE.fullmatch(" ".join(options)):
        kind = "linear"
    questions.append(
        Question(
            id=f"q{len(questions) + 1}",
            number=int(raw["number"]),
            title=title,
            kind=kind,
            required=bool(raw["required"]),
            options=options,
            section=raw["section"],
            scale_min_label=str(raw.get("scale_min_label", "")),
            scale_max_label=str(raw.get("scale_max_label", "")),
        )
    )


def parse_google_forms_pdf(source: bytes | BinaryIO) -> list[Question]:
    stream = io.BytesIO(source) if isinstance(source, bytes) else source
    questions: list[Question] = []
    current: dict | None = None
    current_section = "General"
    collecting_options = False

    with pdfplumber.open(stream) as document:
        for page in document.pages:
            for raw_line in (page.extract_text(layout=True) or "").splitlines():
                line = _clean(raw_line)
                if _is_noise(line):
                    continue
                if SECTION_RE.match(line):
                    _finalize(current, questions)
                    current = None
                    collecting_options = False
                    current_section = line
                    continue
                match = QUESTION_RE.match(line)
                if match:
                    _finalize(current, questions)
                    question_text = SECONDARY_NUMBER_RE.sub("", match.group(2), count=1)
                    current = {
                        "number": int(match.group(1)),
                        "title_parts": [question_text],
                        "kind": "unknown",
                        "required": question_text.rstrip().endswith("*"),
                        "options": [],
                        "section": current_section,
                        "scale_min_label": "",
                        "scale_max_label": "",
                    }
                    collecting_options = False
                    continue
                if current is None:
                    continue
                if line.startswith("Marca solo un óvalo") or line.startswith("Marca solo un ovalo"):
                    current["kind"] = "single"
                    collecting_options = True
                    continue
                if line.startswith("Selecciona todos los que correspondan"):
                    current["kind"] = "multiple"
                    collecting_options = True
                    continue
                if line.startswith("Salta a la pregunta"):
                    continue
                if collecting_options:
                    if SCALE_RE.fullmatch(line):
                        current["kind"] = "linear"
                        current["options"] = line.split()
                        continue
                    if current["kind"] == "linear" and not line.startswith("Otro"):
                        label_parts = [
                            _clean(part)
                            for part in re.split(r"\s{2,}", raw_line.strip())
                            if _clean(part)
                        ]
                        if len(label_parts) >= 2:
                            current["scale_min_label"] = label_parts[0]
                            current["scale_max_label"] = label_parts[-1]
                        continue
                    current["options"].append(line)
                else:
                    current["title_parts"].append(line)
                    current["required"] = current["required"] or line.rstrip().endswith("*")
    _finalize(current, questions)
    return questions


def render_pdf_preview(source: bytes, max_pages: int = 3) -> list[bytes]:
    rendered: list[bytes] = []
    with pdfplumber.open(io.BytesIO(source)) as document:
        for page in document.pages[:max_pages]:
            buffer = io.BytesIO()
            page.to_image(resolution=100).save(buffer, format="PNG")
            rendered.append(buffer.getvalue())
    return rendered
