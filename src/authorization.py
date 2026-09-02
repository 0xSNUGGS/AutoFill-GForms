from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
AUTH_FILE = DATA_DIR / "authorized_forms.json"


def validate_form_url(url: str) -> str:
    value = url.strip()
    parsed = urlparse(value)
    allowed = (
        parsed.scheme == "https"
        and (
            parsed.netloc == "forms.gle"
            or (parsed.netloc == "docs.google.com" and "/forms/" in parsed.path)
        )
    )
    if not allowed:
        raise ValueError("Debe indicar un enlace HTTPS público de Google Forms.")
    if "/edit" in parsed.path:
        raise ValueError("Use el enlace para responder, no el enlace de edición.")
    return value


def _fingerprint(url: str) -> str:
    return hashlib.sha256(validate_form_url(url).encode("utf-8")).hexdigest()


def authorize_form(url: str, label: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    records = {}
    if AUTH_FILE.exists():
        records = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    records[_fingerprint(url)] = {"label": label.strip() or "Formulario de pruebas", "url": url.strip()}
    AUTH_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def is_authorized(url: str) -> bool:
    if not AUTH_FILE.exists():
        return False
    records = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    return _fingerprint(url) in records

