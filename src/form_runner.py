from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Callable

from .authorization import is_authorized, validate_form_url
from .models import Question
from .run_store import RunStore


class FormAutomationError(RuntimeError):
    pass


class AutomationBlocked(FormAutomationError):
    pass


@dataclass(slots=True)
class RunResult:
    requested: int
    successful: int
    failed: int
    stopped: bool
    log_path: str
    failed_indices: list[int]


def normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"^\s*\d+\.\s*", "", normalized)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def _option_text(locator: Any) -> str:
    for attribute in ("data-value", "aria-label"):
        value = locator.get_attribute(attribute)
        if value:
            return value
    try:
        return locator.inner_text()
    except Exception:
        return ""


def _find_option(block: Any, role: str, expected: str) -> Any:
    candidates = block.locator(f'[role="{role}"]:visible')
    expected_normalized = normalize(expected).rstrip(":")
    best = None
    best_score = 0.0
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        actual = normalize(_option_text(candidate)).rstrip(":")
        score = 1.0 if actual == expected_normalized else SequenceMatcher(None, expected_normalized, actual).ratio()
        if score > best_score:
            best, best_score = candidate, score
    if best is None or best_score < 0.66:
        raise FormAutomationError(f"No se encontró la opción '{expected}'.")
    return best


def _question_score(question: Question, block_text: str) -> float:
    expected = normalize(question.title)
    actual = normalize(block_text)
    if not expected or not actual:
        return 0.0
    if expected in actual or expected[:100] in actual:
        return 1.0
    return SequenceMatcher(None, expected[:240], actual[:240]).ratio()


def _fill_question(block: Any, question: Question, answer: dict[str, Any]) -> None:
    if question.kind in ("single", "linear"):
        selected = answer.get("selected", [])
        if selected:
            _find_option(block, "radio", selected[0]).click()
    elif question.kind == "multiple":
        for value in answer.get("selected", []):
            _find_option(block, "checkbox", value).click()
    else:
        value = str(answer.get("text", ""))
        fields = block.locator('textarea:visible, input[type="text"]:visible')
        if value and fields.count():
            fields.first.fill(value)
    other_text = str(answer.get("other_text", "")).strip()
    if other_text:
        fields = block.locator('input[type="text"]:visible')
        if not fields.count():
            raise FormAutomationError(f"No apareció el campo de texto para 'Otro' en {question.title}.")
        fields.last.fill(other_text)


def _has_captcha(page: Any) -> bool:
    return page.locator('iframe[src*="recaptcha"], iframe[src*="captcha"]').count() > 0


def _visible_button(page: Any, names: tuple[str, ...]) -> Any | None:
    buttons = page.locator('[role="button"]:visible, button:visible')
    normalized_names = {normalize(name) for name in names}
    for index in range(buttons.count()):
        button = buttons.nth(index)
        if normalize(button.inner_text()) in normalized_names:
            return button
    return None


def _fill_visible_page(page: Any, questions: list[Question], profile: dict[str, Any], completed: set[str]) -> int:
    blocks = page.locator('div[role="listitem"]:visible')
    filled = 0
    for block_index in range(blocks.count()):
        block = blocks.nth(block_index)
        block_text = block.inner_text()
        candidates = [question for question in questions if question.id not in completed]
        if not candidates:
            break
        question = max(candidates, key=lambda item: _question_score(item, block_text))
        score = _question_score(question, block_text)
        if score < 0.52:
            continue
        answer = profile["answers"].get(question.id, {})
        _fill_question(block, question, answer)
        completed.add(question.id)
        filled += 1
    return filled


def _submit_profile(page: Any, url: str, questions: list[Question], profile: dict[str, Any], submit: bool) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_timeout(700)
    completed: set[str] = set()
    for _ in range(30):
        if _has_captcha(page):
            raise AutomationBlocked("Google Forms solicitó un CAPTCHA; la ejecución fue detenida.")
        _fill_visible_page(page, questions, profile, completed)
        submit_button = _visible_button(page, ("Enviar", "Submit"))
        next_button = _visible_button(page, ("Siguiente", "Next"))
        if submit_button is not None:
            if not submit:
                page.wait_for_timeout(3000)
                return
            submit_button.click()
            page.wait_for_timeout(900)
            body = normalize(page.locator("body").inner_text())
            if not any(message in body for message in ("se registro tu respuesta", "tu respuesta se ha registrado", "response has been recorded")):
                if _has_captcha(page):
                    raise AutomationBlocked("Google Forms solicitó un CAPTCHA después del envío.")
                raise FormAutomationError("El formulario no confirmó el registro de la respuesta.")
            return
        if next_button is None:
            raise FormAutomationError("No se encontró el botón Siguiente o Enviar.")
        next_button.click()
        page.wait_for_timeout(650)
    raise FormAutomationError("El formulario superó el máximo de secciones permitido.")


def run_responses(
    form_url: str,
    questions: list[Question],
    profiles: list[dict[str, Any]],
    run_id: str,
    submit: bool,
    headless: bool,
    delay_seconds: float = 1.0,
    progress: Callable[[int, int, str], None] | None = None,
) -> RunResult:
    url = validate_form_url(form_url)
    if not is_authorized(url):
        raise FormAutomationError("El formulario no está autorizado localmente como formulario de pruebas.")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise FormAutomationError("Playwright no está instalado. Ejecute: playwright install chromium") from error

    store = RunStore(run_id)
    successful = 0
    failed = 0
    failed_indices: list[int] = []
    stopped = False
    selected_profiles = profiles if submit else profiles[:1]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(locale="es-PY")
        page = context.new_page()
        try:
            for position, profile in enumerate(selected_profiles, start=1):
                try:
                    _submit_profile(page, url, questions, profile, submit=submit)
                    successful += 1
                    store.append({"index": profile["index"], "status": "success" if submit else "validated"})
                    message = "Respuesta enviada" if submit else "Validación completada sin enviar"
                except AutomationBlocked as error:
                    failed += 1
                    failed_indices.append(int(profile["index"]))
                    stopped = True
                    store.append({"index": profile["index"], "status": "blocked", "error": str(error)})
                    if progress:
                        progress(position, len(selected_profiles), str(error))
                    break
                except Exception as error:
                    failed += 1
                    failed_indices.append(int(profile["index"]))
                    store.append({"index": profile["index"], "status": "failed", "error": str(error)})
                    message = str(error)
                if progress:
                    progress(position, len(selected_profiles), message)
                if submit and position < len(selected_profiles):
                    time.sleep(max(0.5, delay_seconds))
        finally:
            context.close()
            browser.close()
    return RunResult(
        requested=len(selected_profiles),
        successful=successful,
        failed=failed,
        stopped=stopped,
        log_path=str(store.path),
        failed_indices=failed_indices,
    )
