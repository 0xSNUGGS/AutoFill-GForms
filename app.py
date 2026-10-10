from __future__ import annotations

import csv
import html
import io
import json
import random
import re
import time
import uuid

import streamlit as st

from src.authorization import authorize_form, is_authorized, validate_form_url
from src.form_runner import FormAutomationError, run_responses
from src.form_parser import FormParsingError, parse_google_form_url
from src.distribution_component import distribution_editor, register_distribution_component
from src.generator import (
    ConfigurationError,
    UNANSWERED_KEY,
    generate_responses,
    largest_remainder,
    planned_option_count,
    summarize,
    validate_condition_graph,
)
from src.models import ConditionRule, Question, QUESTION_KINDS
from src.pdf_parser import parse_google_forms_pdf, render_pdf_preview


st.set_page_config(page_title="FormsScript", page_icon="🧪", layout="wide")
register_distribution_component()


KIND_LABELS = {
    "single": "Selección única",
    "multiple": "Selección múltiple",
    "linear": "Escala lineal",
    "grid": "Cuadrícula de opción múltiple",
    "text": "Texto corto",
    "paragraph": "Párrafo",
}


def equal_weights(options: list[str]) -> dict[str, float]:
    if not options:
        return {}
    base = round(100 / len(options), 2)
    result = {option: base for option in options}
    result[options[-1]] = round(100 - sum(result[option] for option in options[:-1]), 2)
    return result


def default_config(question: Question) -> dict:
    if question.kind in ("single", "linear"):
        return {"mode": "percentage", "weights": equal_weights(question.options), "counts": {}, "other_values": []}
    if question.kind == "multiple":
        return {
            "mode": "percentage",
            "weights": {option: 30.0 for option in question.options},
            "counts": {},
            "minimum": 1 if question.required else 0,
            "maximum": max(1, len(question.options)),
            "other_values": [],
        }
    if question.kind == "grid":
        return {
            "row_configs": {
                row: {
                    "mode": "percentage",
                    "weights": equal_weights(question.options),
                    "counts": {},
                    "other_values": [],
                }
                for row in question.rows
            }
        }
    return {"values": []}


def ensure_state() -> None:
    defaults = {
        "questions": [],
        "configs": {},
        "conditions": [],
        "profiles": [],
        "preview_images": [],
        "last_failed": [],
        "last_result": None,
        "condition_drafts": {},
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def sync_configs(questions: list[Question]) -> None:
    configs = st.session_state.configs
    valid_ids = {question.id for question in questions}
    for key in list(configs):
        if key not in valid_ids:
            del configs[key]
    for question in questions:
        current = configs.setdefault(question.id, default_config(question))
        if question.kind == "grid":
            row_configs = current.setdefault("row_configs", {})
            for row in list(row_configs):
                if row not in question.rows:
                    del row_configs[row]
            defaults = default_config(question)["row_configs"]
            for row in question.rows:
                row_config = row_configs.setdefault(row, defaults[row])
                weights = row_config.setdefault("weights", {})
                counts = row_config.setdefault("counts", {})
                row_config.setdefault("mode", "percentage")
                for option in list(weights):
                    if option not in question.options:
                        del weights[option]
                for option in list(counts):
                    if option not in question.options:
                        del counts[option]
                row_defaults = defaults[row]["weights"]
                for option in question.options:
                    weights.setdefault(option, row_defaults.get(option, 0.0))
                    counts.setdefault(option, 0)
            continue
        if question.kind in ("single", "linear", "multiple"):
            weights = current.setdefault("weights", {})
            counts = current.setdefault("counts", {})
            current.setdefault("mode", "percentage")
            for option in list(weights):
                if option not in question.options:
                    del weights[option]
            for option in list(counts):
                if option not in question.options:
                    del counts[option]
            defaults = default_config(question)["weights"]
            for option in question.options:
                weights.setdefault(option, defaults.get(option, 0.0))
                counts.setdefault(option, 0)
            current.setdefault("other_values", [])
        else:
            configs[question.id] = {"values": current.get("values", [])}


def split_values(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[;\r\n]+", value) if item.strip()]


def format_percentage(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def distribution_component_key(question: Question, sample_size: int) -> str:
    signature = uuid.uuid5(
        uuid.NAMESPACE_URL,
        json.dumps(
            [question.kind, question.required, question.options, question.rows],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    ).hex[:10]
    return f"distribution_{question.id}_{sample_size}_{signature}"


def _rescale_counts(total: int, values: dict[str, int]) -> dict[str, int]:
    """Scale an existing exclusive allocation to an exact new sample size."""

    assigned = sum(max(0, int(value)) for value in values.values())
    if not values:
        return {}
    if assigned <= 0:
        base, remainder = divmod(total, len(values))
        return {
            key: base + (1 if index < remainder else 0)
            for index, key in enumerate(values)
        }
    exact = {key: total * max(0, int(value)) / assigned for key, value in values.items()}
    result = {key: int(value) for key, value in exact.items()}
    remainder = total - sum(result.values())
    order = sorted(exact, key=lambda key: (exact[key] - result[key], key), reverse=True)
    for key in order[:remainder]:
        result[key] += 1
    return result


def _graphical_counts(question: Question, config: dict, sample_size: int) -> dict[str, int]:
    """Return integer counts and migrate older percentage configurations."""

    previous_total = max(1, int(config.get("basis_total", sample_size)))
    if question.kind in ("single", "linear", "grid"):
        keys = list(question.options)
        if not question.required:
            keys.append(UNANSWERED_KEY)
        if config.get("mode") == "count" and config.get("counts"):
            values = {key: max(0, int(config["counts"].get(key, 0))) for key in question.options}
            if not question.required:
                values[UNANSWERED_KEY] = max(0, int(config.get("unanswered_count", 0)))
            if previous_total != sample_size or sum(values.values()) != sample_size:
                values = _rescale_counts(sample_size, values)
        else:
            values = largest_remainder(sample_size, config.get("weights", equal_weights(question.options)))
            if not question.required:
                values[UNANSWERED_KEY] = 0
        return {key: values.get(key, 0) for key in keys}

    if config.get("mode") == "count" and config.get("counts"):
        if previous_total == sample_size:
            return {
                option: min(sample_size, max(0, int(config["counts"].get(option, 0))))
                for option in question.options
            }
        return {
            option: min(
                sample_size,
                max(0, round(sample_size * int(config["counts"].get(option, 0)) / previous_total)),
            )
            for option in question.options
        }
    return {
        option: round(sample_size * float(config.get("weights", {}).get(option, 0.0)) / 100)
        for option in question.options
    }


def _store_graphical_counts(
    question: Question,
    config: dict,
    counts: dict[str, int],
    sample_size: int,
    input_mode: str,
) -> None:
    config["mode"] = "count"
    config["display_mode"] = input_mode
    config["basis_total"] = sample_size
    config["counts"] = {
        option: min(sample_size, max(0, int(counts.get(option, 0))))
        for option in question.options
    }
    config["weights"] = {
        option: round(config["counts"][option] * 100 / sample_size, 8)
        for option in question.options
    }
    if question.kind in ("single", "linear", "grid"):
        config["unanswered_count"] = (
            min(sample_size, max(0, int(counts.get(UNANSWERED_KEY, 0))))
            if not question.required
            else 0
        )


def response_exports(questions: list[Question], profiles: list[dict]) -> tuple[bytes, bytes]:
    json_bytes = json.dumps(profiles, ensure_ascii=False, indent=2).encode("utf-8")
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["respuesta"] + [question.title for question in questions])
    for profile in profiles:
        row = [profile["index"]]
        for question in questions:
            answer = profile["answers"].get(question.id, {})
            if "grid" in answer:
                value = " | ".join(
                    f"{grid_row}: {answer['grid'].get(grid_row, 'Sin respuesta')}"
                    for grid_row in question.rows
                )
            elif "selected" in answer:
                value = " | ".join(answer["selected"])
                if answer.get("other_text"):
                    value += f": {answer['other_text']}"
            else:
                value = answer.get("text", "")
            row.append(value)
        writer.writerow(row)
    return json_bytes, output.getvalue().encode("utf-8-sig")


def render_summary_table(rows: list[dict]) -> None:
    if not rows:
        st.info("No hay respuestas para resumir.")
        return
    headers = ("Pregunta", "Respuesta", "Cantidad", "Porcentaje")
    header_html = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body_html = "".join(
        "<tr>"
        + "".join(
            f"<td>{html.escape(str(row.get(header, '')))}</td>"
            for header in headers
        )
        + "</tr>"
        for row in rows
    )
    st.html(
        """
        <style>
          .forms-summary { overflow-x: auto; border: 1px solid rgba(128,128,128,.28); border-radius: 10px; }
          .forms-summary table { width: 100%; border-collapse: collapse; font: inherit; }
          .forms-summary th, .forms-summary td { padding: 9px 12px; border-bottom: 1px solid rgba(128,128,128,.22); text-align: left; }
          .forms-summary th { background: rgba(128,128,128,.12); position: sticky; top: 0; }
          .forms-summary td:nth-child(3), .forms-summary td:nth-child(4) { text-align: right; white-space: nowrap; }
          .forms-summary tr:last-child td { border-bottom: 0; }
        </style>
        <div class="forms-summary"><table><thead><tr>"""
        + header_html
        + "</tr></thead><tbody>"
        + body_html
        + "</tbody></table></div>"
    )


def _estimated_trigger_count(question: Question, option: str, sample_size: int) -> int:
    config = st.session_state.configs.get(question.id, default_config(question))
    return planned_option_count(
        sample_size,
        config,
        option,
        multiple=question.kind == "multiple",
    )


def _rule_summary(rule: ConditionRule, by_id: dict[str, Question]) -> str:
    target = by_id.get(rule.target_question_id)
    target_title = target.title[:55] if target else "Pregunta eliminada"
    trigger = ", ".join(rule.trigger_values)
    if rule.action == "force_answer":
        action = f"asignar {', '.join(rule.target_values)}"
    elif rule.action == "unanswered":
        action = "dejar sin responder"
    else:
        action = "aplicar distribución especial"
    return f"{trigger} → {target_title} → {action}"


def condition_from_value(value: object) -> ConditionRule:
    if isinstance(value, dict):
        return ConditionRule.from_dict(value)
    if hasattr(value, "to_dict"):
        return ConditionRule.from_dict(value.to_dict())
    return ConditionRule.from_dict(
        {
            "id": getattr(value, "id"),
            "trigger_question_id": getattr(value, "trigger_question_id"),
            "trigger_values": getattr(value, "trigger_values", []),
            "target_question_id": getattr(value, "target_question_id"),
            "target_config": getattr(value, "target_config", {}),
            "match_mode": getattr(value, "match_mode", "any"),
        }
    )


def render_inline_conditions(
    source: Question,
    all_questions: list[Question],
    sample_size: int,
) -> None:
    if not source.options:
        st.caption("Las condiciones por opción requieren respuestas seleccionables.")
        return
    by_id = {question.id: question for question in all_questions}
    rules = [
        condition_from_value(value)
        for value in st.session_state.conditions
    ]
    source_rules = [rule for rule in rules if rule.trigger_question_id == source.id]
    enabled = st.checkbox(
        "Condicionar opciones",
        value=bool(source_rules and any(rule.enabled for rule in source_rules)),
        key=f"conditions_enabled_{source.id}",
    )
    if source_rules:
        changed = False
        for rule in source_rules:
            if rule.enabled != enabled:
                rule.enabled = enabled
                changed = True
        if changed:
            st.session_state.conditions = [rule.to_dict() for rule in rules]
    if not enabled:
        st.caption(
            f"{len(source_rules)} regla(s) guardada(s)" if source_rules else "Sin condiciones configuradas"
        )
        return

    for rule in source_rules:
        row = st.columns([8, 1])
        row[0].caption(_rule_summary(rule, by_id))
        if row[1].button("×", key=f"delete_inline_condition_{rule.id}", help="Eliminar condición"):
            st.session_state.conditions = [
                value
                for value in st.session_state.conditions
                if condition_from_value(value).id != rule.id
            ]
            st.session_state.profiles = []
            st.rerun()

    try:
        source_position = next(index for index, question in enumerate(all_questions) if question.id == source.id)
    except StopIteration:
        source_position = -1
    targets = [
        question
        for question in all_questions[source_position + 1 :]
        if question.id != source.id and question.kind not in ("multiple", "grid")
    ]
    if not targets:
        st.info("No hay preguntas posteriores compatibles para condicionar.")
        return

    st.markdown("**Nueva regla por opción**")
    trigger_value = st.selectbox(
        "Si responde",
        source.options,
        key=f"condition_trigger_value_{source.id}",
    )
    estimated = _estimated_trigger_count(source, trigger_value, sample_size)
    st.caption(f"Población estimada de esta opción: {estimated} de {sample_size}.")
    sections = list(dict.fromkeys(question.section for question in targets))
    target_section = st.selectbox(
        "Sección destino",
        sections,
        key=f"condition_target_section_{source.id}",
    )
    section_targets = [question for question in targets if question.section == target_section]
    target_id = st.selectbox(
        "Pregunta destino",
        [question.id for question in section_targets],
        format_func=lambda value: by_id[value].title,
        key=f"condition_target_question_{source.id}",
    )
    target = by_id[target_id]
    actions = ["force_answer", "distribution"]
    if not target.required:
        actions.append("unanswered")
    action = st.selectbox(
        "Acción",
        actions,
        format_func=lambda value: {
            "force_answer": "Fijar respuesta",
            "distribution": "Aplicar distribución especial",
            "unanswered": "Dejar sin responder",
        }[value],
        key=f"condition_action_{source.id}",
    )
    target_values: list[str] = []
    target_config: dict = {}
    if action == "force_answer":
        if target.kind in ("single", "linear"):
            target_values = [
                st.selectbox(
                    "Respuesta fijada",
                    target.options,
                    key=f"condition_fixed_value_{source.id}_{target.id}",
                )
            ]
            if target_values[0].casefold().rstrip(":").strip() == "otro":
                target_config["other_values"] = split_values(
                    st.text_area(
                        "Textos para Otro, separados por ; o salto de línea",
                        key=f"condition_fixed_other_{source.id}_{target.id}",
                    )
                )
        else:
            fixed_text = st.text_input(
                "Texto fijado",
                key=f"condition_fixed_text_{source.id}_{target.id}",
            ).strip()
            target_values = [fixed_text] if fixed_text else []
    elif action == "distribution":
        if target.kind not in ("single", "linear"):
            st.warning("Las distribuciones especiales están disponibles para selección única y escalas.")
        else:
            draft_key = f"{source.id}:{trigger_value}:{target.id}"
            draft = st.session_state.condition_drafts.setdefault(draft_key, default_config(target))
            draft_total = max(1, estimated)
            draft_counts = _graphical_counts(target, draft, draft_total)
            graphical_options = [{"key": option, "label": option} for option in target.options]
            result = distribution_editor(
                kind="exclusive",
                options=graphical_options,
                counts=draft_counts,
                total=draft_total,
                input_mode=str(draft.get("display_mode", "percentage")),
                key=f"condition_distribution_{source.id}_{target.id}_{trigger_value}_{draft_total}",
            )
            if result:
                draft_counts = result.get("counts", draft_counts)
                draft["display_mode"] = str(result.get("inputMode", "percentage"))
            draft["mode"] = "percentage"
            draft["weights"] = {
                option: 100 * int(draft_counts.get(option, 0)) / draft_total
                for option in target.options
            }
            if target.options:
                draft["weights"][target.options[-1]] += 100 - sum(draft["weights"].values())
            target_config = dict(draft)

    if st.button("Agregar condición", type="primary", key=f"add_condition_{source.id}"):
        if action == "force_answer" and not target_values:
            st.error("Debe indicar la respuesta que será fijada.")
        elif action == "distribution" and target.kind not in ("single", "linear"):
            st.error("La pregunta destino no admite una distribución especial.")
        else:
            new_rule = ConditionRule(
                id=uuid.uuid4().hex[:10],
                trigger_question_id=source.id,
                trigger_values=[trigger_value],
                target_question_id=target.id,
                target_config=target_config,
                action=action,
                target_values=target_values,
                target_section=target.section,
                priority=len(st.session_state.conditions),
            )
            proposed = rules + [new_rule]
            try:
                validate_condition_graph(all_questions, proposed)
            except ConfigurationError as error:
                st.error(str(error))
            else:
                st.session_state.conditions.append(new_rule.to_dict())
                st.session_state.profiles = []
                st.rerun()


def render_question_editor(question: Question, sample_size: int, all_questions: list[Question]) -> Question:
    with st.expander(f"{question.number}. {question.title[:110]}", expanded=False):
        title = st.text_area("Pregunta", question.title, key=f"title_{question.id}")
        left, middle = st.columns(2)
        with left:
            kind = st.selectbox(
                "Tipo",
                QUESTION_KINDS,
                index=QUESTION_KINDS.index(question.kind),
                format_func=lambda value: KIND_LABELS[value],
                key=f"kind_{question.id}",
            )
        with middle:
            required = st.checkbox("Obligatoria", question.required, key=f"required_{question.id}")
            condition_slot = st.container()
        options = question.options
        rows = question.rows
        if kind in ("single", "multiple", "linear", "grid"):
            raw_options = st.text_area(
                "Columnas, una por línea" if kind == "grid" else "Opciones, una por línea",
                "\n".join(options),
                key=f"options_{question.id}",
            )
            options = [item.strip() for item in raw_options.splitlines() if item.strip()]
        if kind == "grid":
            raw_rows = st.text_area(
                "Filas, una por línea",
                "\n".join(rows),
                key=f"rows_{question.id}",
            )
            rows = [item.strip() for item in raw_rows.splitlines() if item.strip()]
        scale_min_label = getattr(question, "scale_min_label", "")
        scale_max_label = getattr(question, "scale_max_label", "")
        if kind == "linear":
            label_left, label_right = st.columns(2)
            scale_min_label = label_left.text_input(
                f"Significado de {options[0] if options else 'mínimo'}",
                value=scale_min_label,
                key=f"scale_min_{question.id}",
                placeholder="Ej.: Muy difícil",
            )
            scale_max_label = label_right.text_input(
                f"Significado de {options[-1] if options else 'máximo'}",
                value=scale_max_label,
                key=f"scale_max_{question.id}",
                placeholder="Ej.: Muy fácil",
            )
        updated = Question(
            id=question.id,
            number=question.number,
            title=title.strip(),
            kind=kind,
            required=required,
            options=options,
            section=question.section,
            scale_min_label=scale_min_label.strip() if kind == "linear" else "",
            scale_max_label=scale_max_label.strip() if kind == "linear" else "",
            rows=rows if kind == "grid" else [],
        )
        with condition_slot:
            if kind == "grid":
                st.caption("Las condiciones no están disponibles para cuadrículas.")
            else:
                condition_count = sum(
                    1
                    for value in st.session_state.conditions
                    if condition_from_value(value).trigger_question_id == updated.id
                )
                with st.popover(
                    f"Condiciones por opción ({condition_count})",
                    use_container_width=True,
                ):
                    render_inline_conditions(updated, all_questions, sample_size)
        sync_configs([updated] + [q for q in current_questions() if q.id != updated.id])
        config = st.session_state.configs[question.id]
        if kind in ("single", "linear"):
            counts = _graphical_counts(updated, config, sample_size)
            _store_graphical_counts(
                updated,
                config,
                counts,
                sample_size,
                str(config.get("display_mode", "percentage")),
            )
            graphical_options = [{"key": option, "label": option} for option in options]
            if kind == "linear" and graphical_options:
                if updated.scale_min_label:
                    graphical_options[0]["label"] = f"{options[0]} — {updated.scale_min_label}"
                if updated.scale_max_label:
                    graphical_options[-1]["label"] = f"{options[-1]} — {updated.scale_max_label}"
            if not required:
                graphical_options.append({"key": UNANSWERED_KEY, "label": "Sin responder"})
            st.caption(
                f"Distribución exclusiva · 1 respuesta equivale a {format_percentage(100 / sample_size)}% "
                "· arrastra los separadores o escribe un valor exacto."
            )
            result = distribution_editor(
                kind="exclusive",
                options=graphical_options,
                counts=counts,
                total=sample_size,
                input_mode=str(config.get("display_mode", "percentage")),
                key=distribution_component_key(updated, sample_size),
            )
            if result:
                result_counts = result.get("counts", counts)
                result_mode = str(result.get("inputMode", "percentage"))
                changed = result_counts != counts or result_mode != str(config.get("display_mode", "percentage"))
                _store_graphical_counts(
                    updated,
                    config,
                    result_counts,
                    sample_size,
                    result_mode,
                )
                if changed:
                    st.rerun()
        elif kind == "multiple":
            first, second = st.columns(2)
            minimum_floor = 1 if required else 0
            maximum_options = max(1, len(options))
            config["minimum"] = first.number_input(
                "Mínimo de opciones",
                minimum_floor,
                maximum_options,
                min(maximum_options, max(minimum_floor, int(config.get("minimum", minimum_floor)))),
                key=f"min_{question.id}",
            )
            config["maximum"] = second.number_input(
                "Máximo de opciones",
                max(1, int(config["minimum"])),
                max(1, len(options)),
                min(max(1, len(options)), int(config.get("maximum", max(1, len(options))))),
                key=f"max_{question.id}",
            )
            counts = _graphical_counts(updated, config, sample_size)
            _store_graphical_counts(
                updated,
                config,
                counts,
                sample_size,
                str(config.get("display_mode", "percentage")),
            )
            st.caption(
                f"Cada barra es independiente y tiene un máximo de 100% · "
                f"1 participante equivale a {format_percentage(100 / sample_size)}%."
            )
            result = distribution_editor(
                kind="multiple",
                options=[{"key": option, "label": option} for option in options],
                counts=counts,
                total=sample_size,
                input_mode=str(config.get("display_mode", "percentage")),
                minimum=int(config["minimum"]),
                maximum=int(config["maximum"]),
                key=distribution_component_key(updated, sample_size),
            )
            if result:
                result_counts = result.get("counts", counts)
                result_mode = str(result.get("inputMode", "percentage"))
                changed = result_counts != counts or result_mode != str(config.get("display_mode", "percentage"))
                _store_graphical_counts(
                    updated,
                    config,
                    result_counts,
                    sample_size,
                    result_mode,
                )
                if changed:
                    st.rerun()
        elif kind == "grid":
            if not options or not rows:
                st.warning("La cuadrícula necesita al menos una fila y una columna.")
            else:
                st.caption(
                    f"Cada fila tiene una distribución exclusiva · 1 respuesta equivale a "
                    f"{format_percentage(100 / sample_size)}%."
                )
                row_configs = config.setdefault("row_configs", {})
                for grid_row in rows:
                    st.markdown(f"**{grid_row}**")
                    row_config = row_configs.setdefault(
                        grid_row,
                        {
                            "mode": "percentage",
                            "weights": equal_weights(options),
                            "counts": {},
                        },
                    )
                    counts = _graphical_counts(updated, row_config, sample_size)
                    _store_graphical_counts(
                        updated,
                        row_config,
                        counts,
                        sample_size,
                        str(row_config.get("display_mode", "percentage")),
                    )
                    graphical_options = [{"key": option, "label": option} for option in options]
                    if not required:
                        graphical_options.append({"key": UNANSWERED_KEY, "label": "Sin responder"})
                    row_key = uuid.uuid5(uuid.NAMESPACE_URL, grid_row).hex[:10]
                    result = distribution_editor(
                        kind="exclusive",
                        options=graphical_options,
                        counts=counts,
                        total=sample_size,
                        input_mode=str(row_config.get("display_mode", "percentage")),
                        key=f"{distribution_component_key(updated, sample_size)}_{row_key}",
                    )
                    if result:
                        result_counts = result.get("counts", counts)
                        result_mode = str(result.get("inputMode", "percentage"))
                        changed = result_counts != counts or result_mode != str(
                            row_config.get("display_mode", "percentage")
                        )
                        _store_graphical_counts(
                            updated,
                            row_config,
                            result_counts,
                            sample_size,
                            result_mode,
                        )
                        if changed:
                            st.rerun()
        else:
            raw_values = st.text_area(
                "Respuestas separadas por punto y coma (cada aparición se usa una vez)",
                ";".join(config.get("values", [])),
                key=f"texts_{question.id}",
            )
            config["values"] = split_values(raw_values)
            st.caption(f"Respuestas proporcionadas: {len(config['values'])}")
        if kind in ("single", "multiple", "linear") and any(
            option.casefold().rstrip(":").strip() == "otro" for option in options
        ):
            raw_other = st.text_area(
                "Textos para Otro, separados por punto y coma o salto de línea",
                ";".join(config.get("other_values", [])),
                key=f"other_{question.id}",
            )
            config["other_values"] = split_values(raw_other)
            other_option = next(
                option for option in options if option.casefold().rstrip(":").strip() == "otro"
            )
            required_other = planned_option_count(
                sample_size,
                config,
                other_option,
                multiple=kind == "multiple",
            )
            provided_other = len(config["other_values"])
            missing_other = max(0, required_other - provided_other)
            st.caption(
                f"Textos para Otro: {provided_other} proporcionados de {required_other} necesarios"
                + (f" · faltan {missing_other}" if missing_other else " · completos")
            )
        return updated


def current_questions() -> list[Question]:
    migrated: list[Question] = []
    for value in st.session_state.questions:
        if isinstance(value, dict):
            migrated.append(Question.from_dict(value))
        elif hasattr(value, "to_dict"):
            # Streamlit puede conservar instancias creadas antes de que el
            # modelo Question incorporara campos nuevos. Reconstruirlas aplica
            # los valores predeterminados de la versión actual.
            migrated.append(Question.from_dict(value.to_dict()))
        else:
            migrated.append(
                Question.from_dict(
                    {
                        "id": getattr(value, "id"),
                        "number": getattr(value, "number"),
                        "title": getattr(value, "title"),
                        "kind": getattr(value, "kind", "text"),
                        "required": getattr(value, "required", False),
                        "options": getattr(value, "options", []),
                        "rows": getattr(value, "rows", []),
                        "section": getattr(value, "section", "General"),
                    }
                )
            )
    return migrated


def render_conditions(questions: list[Question]) -> None:
    st.subheader("Resumen de condiciones")
    st.caption(
        "Las reglas se configuran dentro de cada pregunta. Aquí puede revisar dependencias, "
        "reservas y conflictos globales."
    )
    by_id = {question.id: question for question in questions}
    rules: list[ConditionRule] = []
    for raw_rule in st.session_state.conditions:
        rule = condition_from_value(raw_rule)
        rules.append(rule)
    if not rules:
        st.info("Todavía no hay condiciones configuradas.")
        return
    try:
        validate_condition_graph(questions, rules)
    except ConfigurationError as error:
        st.error(str(error))
    else:
        st.success("No se detectaron ciclos ni referencias inválidas.")

    for index, rule in enumerate(rules):
        trigger = by_id.get(rule.trigger_question_id)
        target = by_id.get(rule.target_question_id)
        if not trigger or not target:
            st.error(f"La condición {rule.id} referencia una pregunta que ya no existe.")
            continue
        estimated = sum(
            _estimated_trigger_count(trigger, option, int(st.session_state.sample_size))
            for option in rule.trigger_values
        )
        with st.container(border=True):
            header = st.columns([6, 2, 1])
            header[0].markdown(f"**{_rule_summary(rule, by_id)}**")
            header[1].caption(f"Hasta {estimated} participantes")
            enabled = header[2].toggle(
                "Activa",
                value=rule.enabled,
                key=f"global_condition_enabled_{rule.id}",
            )
            if enabled != rule.enabled:
                rule.enabled = enabled
                st.session_state.conditions[index] = rule.to_dict()
                st.session_state.profiles = []
            st.caption(
                f"Origen: P{trigger.number} · Destino: {target.section} / P{target.number} · "
                f"Prioridad {rule.priority + 1}"
            )
            if st.button("Eliminar", key=f"remove_condition_{rule.id}"):
                st.session_state.conditions.pop(index)
                st.session_state.profiles = []
                st.rerun()


def run_automation(url: str, questions: list[Question], profiles: list[dict], submit: bool, headless: bool, delay: float) -> None:
    progress_bar = st.progress(0)
    status = st.empty()

    def update(done: int, total: int, message: str) -> None:
        progress_bar.progress(done / total if total else 1.0)
        status.write(f"{done}/{total}: {message}")

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    try:
        result = run_responses(
            url,
            questions,
            profiles,
            run_id=run_id,
            submit=submit,
            headless=headless,
            delay_seconds=delay,
            progress=update,
        )
    except (FormAutomationError, ValueError) as error:
        st.error(str(error))
        return
    st.session_state.last_result = result
    failed = set(result.failed_indices)
    st.session_state.last_failed = [profile for profile in profiles if profile["index"] in failed]
    if result.stopped:
        st.warning("La ejecución se detuvo por un control de seguridad de Google.")
    elif result.failed:
        st.warning(f"Finalizó con {result.successful} éxitos y {result.failed} fallos.")
    else:
        st.success(f"Operación completada: {result.successful} de {result.requested}.")
    st.caption(f"Registro local: {result.log_path}")


ensure_state()
st.title("FormsScript")
st.caption("Generador y ejecutor para formularios propios destinados a pruebas.")

with st.container(border=True):
    st.subheader("1. Definir muestra y cargar formulario")
    sample_size = st.number_input(
        "Tamaño de la muestra",
        min_value=1,
        max_value=5000,
        value=200,
        step=1,
        key="sample_size",
    )
    st.caption(
        f"Con esta muestra, una respuesta equivale a {format_percentage(100 / int(sample_size))}%. "
        "Puedes cambiarla después y las distribuciones se recalcularán."
    )
    form_url = st.text_input(
        "Enlace de Google Forms (público o de edición)",
        placeholder="https://docs.google.com/forms/d/.../edit",
    )
    uploaded_pdf = st.file_uploader(
        "PDF exportado desde Google Forms (opcional si analiza el enlace)",
        type=("pdf",),
    )
    analyze_link, analyze_pdf = st.columns(2)
    if analyze_link.button("Analizar formulario", type="primary", disabled=not form_url):
        try:
            questions, public_url = parse_google_form_url(form_url)
            st.session_state.questions = [question.to_dict() for question in questions]
            st.session_state.configs = {question.id: default_config(question) for question in questions}
            st.session_state.conditions = []
            st.session_state.profiles = []
            st.session_state.preview_images = (
                render_pdf_preview(uploaded_pdf.getvalue()) if uploaded_pdf is not None else []
            )
            st.session_state["resolved_form_url"] = public_url
            st.success(f"Se detectaron {len(questions)} preguntas desde el formulario.")
        except (FormParsingError, ValueError) as error:
            st.error(f"No fue posible interpretar el formulario: {error}")
    if analyze_pdf.button("Analizar solo el PDF", disabled=uploaded_pdf is None):
        try:
            pdf_bytes = uploaded_pdf.getvalue()
            questions = parse_google_forms_pdf(pdf_bytes)
            if not questions:
                raise ValueError("No se detectaron preguntas en el PDF.")
            st.session_state.questions = [question.to_dict() for question in questions]
            st.session_state.configs = {question.id: default_config(question) for question in questions}
            st.session_state.conditions = []
            st.session_state.profiles = []
            st.session_state.preview_images = render_pdf_preview(pdf_bytes)
            st.success(f"Se detectaron {len(questions)} preguntas.")
        except Exception as error:
            st.error(f"No fue posible interpretar el PDF: {error}")
    resolved_form_url = st.session_state.get("resolved_form_url", "")
    if resolved_form_url and resolved_form_url != form_url:
        st.caption(f"Enlace público resuelto: {resolved_form_url}")

questions = current_questions()
if st.session_state.preview_images:
    with st.expander("Vista del PDF importado"):
        st.image(st.session_state.preview_images, caption=[f"Página {index + 1}" for index in range(len(st.session_state.preview_images))])

if questions:
    generated_seed = random.SystemRandom().randint(1, 2_147_483_647)
    seed = st.number_input("Semilla aleatoria", min_value=1, max_value=2_147_483_647, value=generated_seed, step=1)
    tabs = st.tabs(("Preguntas y distribuciones", "Condiciones", "Generación", "Envío"))

    with tabs[0]:
        edited: list[Question] = []
        for section in dict.fromkeys(question.section for question in questions):
            st.markdown(f"### {section}")
            for question in [item for item in questions if item.section == section]:
                edited.append(render_question_editor(question, int(sample_size), questions))
        st.session_state.questions = [question.to_dict() for question in edited]
        questions = edited

    with tabs[1]:
        render_conditions(questions)

    with tabs[2]:
        if st.button("Generar vista previa", type="primary"):
            try:
                rules = [condition_from_value(value) for value in st.session_state.conditions]
                profiles = generate_responses(
                    questions,
                    st.session_state.configs,
                    rules,
                    int(sample_size),
                    int(seed),
                )
                st.session_state.profiles = profiles
                st.success(f"Se generaron exactamente {len(profiles)} respuestas.")
            except ConfigurationError as error:
                st.error(str(error))
        if st.session_state.profiles:
            profiles = st.session_state.profiles
            render_summary_table(summarize(questions, profiles))
            json_bytes, csv_bytes = response_exports(questions, profiles)
            first, second = st.columns(2)
            first.download_button("Descargar JSON", json_bytes, "respuestas-prueba.json", "application/json")
            second.download_button("Descargar CSV", csv_bytes, "respuestas-prueba.csv", "text/csv")

    with tabs[3]:
        try:
            valid_url = validate_form_url(form_url) if form_url else ""
        except ValueError as error:
            valid_url = ""
            st.error(str(error))
        authorized = bool(valid_url and is_authorized(valid_url))
        if authorized:
            st.success("Este enlace está autorizado localmente como formulario de pruebas.")
        else:
            confirmation = st.checkbox("Confirmo que el formulario es mío y está destinado a pruebas.")
            label = st.text_input("Nombre local del formulario", value="Formulario de pruebas")
            if st.button("Autorizar formulario", disabled=not (valid_url and confirmation)):
                authorize_form(valid_url, label)
                st.success("Formulario autorizado en este equipo.")
                st.rerun()
        headless = st.checkbox("Ejecutar navegador en segundo plano", value=False)
        delay = st.number_input("Pausa entre envíos (segundos)", min_value=0.5, max_value=30.0, value=1.5, step=0.5)
        ready = authorized and bool(st.session_state.profiles)
        first, second = st.columns(2)
        if first.button("Validar primera respuesta sin enviar", disabled=not ready):
            run_automation(valid_url, questions, st.session_state.profiles[:1], False, headless, float(delay))
        execute_confirmation = st.checkbox(
            f"Confirmo el envío de {len(st.session_state.profiles)} respuestas al formulario de pruebas.",
            disabled=not ready,
        )
        if second.button("Enviar todas las respuestas", type="primary", disabled=not (ready and execute_confirmation)):
            run_automation(valid_url, questions, st.session_state.profiles, True, headless, float(delay))
        if st.session_state.last_failed:
            st.warning(f"Quedaron {len(st.session_state.last_failed)} respuestas fallidas disponibles para reintento.")
            if st.button("Reintentar solamente fallidas", disabled=not authorized):
                run_automation(valid_url, questions, st.session_state.last_failed, True, headless, float(delay))
