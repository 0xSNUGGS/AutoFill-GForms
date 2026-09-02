from __future__ import annotations

import math
import random
from collections import Counter, defaultdict, deque
from typing import Any

from .models import ConditionRule, Question


class ConfigurationError(ValueError):
    pass


UNANSWERED_KEY = "__unanswered__"


def largest_remainder(total: int, weights: dict[str, float]) -> dict[str, int]:
    if total < 0:
        raise ConfigurationError("El tamaño no puede ser negativo.")
    if not weights:
        raise ConfigurationError("La distribución no tiene opciones.")
    weight_sum = sum(float(value) for value in weights.values())
    if not math.isclose(weight_sum, 100.0, abs_tol=0.05):
        raise ConfigurationError(f"Los porcentajes deben sumar 100; actualmente suman {weight_sum:.2f}.")
    exact = {key: total * float(value) / 100.0 for key, value in weights.items()}
    counts = {key: math.floor(value) for key, value in exact.items()}
    missing = total - sum(counts.values())
    order = sorted(exact, key=lambda key: (exact[key] - counts[key], key), reverse=True)
    for key in order[:missing]:
        counts[key] += 1
    return counts


def exclusive_counts(total: int, config: dict[str, Any]) -> dict[str, int]:
    if config.get("mode", "percentage") != "count":
        return largest_remainder(total, config.get("weights", {}))
    raw_counts = config.get("counts", {})
    counts: dict[str, int] = {}
    for option, value in raw_counts.items():
        numeric = int(value)
        if numeric < 0 or float(value) != numeric:
            raise ConfigurationError(f"La cantidad de {option} debe ser un entero no negativo.")
        counts[option] = numeric
    unanswered = int(config.get("unanswered_count", 0))
    if unanswered < 0:
        raise ConfigurationError("La cantidad sin responder debe ser un entero no negativo.")
    if unanswered:
        counts[UNANSWERED_KEY] = unanswered
    assigned = sum(counts.values())
    if assigned != total:
        raise ConfigurationError(
            f"Las cantidades deben sumar {total}; actualmente suman {assigned}."
        )
    return counts


def planned_option_count(total: int, config: dict[str, Any], option: str, multiple: bool = False) -> int:
    if config.get("mode", "percentage") == "count":
        return int(config.get("counts", {}).get(option, 0))
    percentage = float(config.get("weights", {}).get(option, 0.0))
    if multiple:
        return round(total * percentage / 100.0)
    return largest_remainder(total, config.get("weights", {})).get(option, 0)


def _selected(answer: dict[str, Any] | None) -> list[str]:
    if not answer:
        return []
    return [str(item) for item in answer.get("selected", [])]


def _matches(answer: dict[str, Any] | None, values: list[str], mode: str) -> bool:
    selected = set(_selected(answer))
    expected = set(values)
    return expected.issubset(selected) if mode == "all" else bool(expected & selected)


def _topological_order(questions: list[Question], rules: list[ConditionRule]) -> list[str]:
    ids = {question.id for question in questions}
    edges: dict[str, set[str]] = defaultdict(set)
    indegree = {question.id: 0 for question in questions}
    for rule in rules:
        if not rule.enabled:
            continue
        if rule.trigger_question_id not in ids or rule.target_question_id not in ids:
            raise ConfigurationError("Una condición referencia una pregunta inexistente.")
        if rule.target_question_id not in edges[rule.trigger_question_id]:
            edges[rule.trigger_question_id].add(rule.target_question_id)
            indegree[rule.target_question_id] += 1
    queue = deque(question.id for question in questions if indegree[question.id] == 0)
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for target in edges[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(order) != len(questions):
        raise ConfigurationError("Las condiciones forman una dependencia circular.")
    return order


def validate_condition_graph(questions: list[Question], rules: list[ConditionRule]) -> None:
    _topological_order(questions, rules)


def _assign_single(
    question: Question,
    config: dict[str, Any],
    rows: list[int],
    profiles: list[dict[str, Any]],
    rng: random.Random,
) -> None:
    counts = exclusive_counts(len(rows), config)
    values = [option for option, count in counts.items() for _ in range(count)]
    rng.shuffle(values)
    rng.shuffle(rows)
    for row, value in zip(rows, values, strict=True):
        profiles[row]["answers"][question.id] = {
            "selected": [] if value == UNANSWERED_KEY else [value]
        }
    _attach_other_text(question, config, rows, profiles, rng)


def _assign_multiple(
    question: Question,
    config: dict[str, Any],
    rows: list[int],
    profiles: list[dict[str, Any]],
    rng: random.Random,
) -> None:
    probabilities = config.get("weights", {})
    configured_counts = config.get("counts", {})
    count_mode = config.get("mode", "percentage") == "count"
    targets: dict[str, int] = {}
    for option in question.options:
        value = configured_counts.get(option, 0) if count_mode else probabilities.get(option, 0)
        if count_mode:
            count = int(value)
            if count < 0 or count > len(rows) or float(value) != count:
                raise ConfigurationError(
                    f"La cantidad de {option} debe ser un entero entre 0 y {len(rows)}."
                )
        else:
            percentage = float(value)
            if not 0 <= percentage <= 100:
                raise ConfigurationError(f"El porcentaje de {option} debe estar entre 0 y 100.")
            count = round(len(rows) * percentage / 100.0)
        targets[option] = count
    minimum = int(config.get("minimum", 1 if question.required else 0))
    maximum = int(config.get("maximum", max(1, len(question.options))))
    if minimum < 0 or maximum < minimum or maximum > len(question.options):
        raise ConfigurationError(
            f"{question.title}: los límites mínimo y máximo de opciones no son válidos."
        )
    selection_total = sum(targets.values())
    if selection_total < len(rows) * minimum or selection_total > len(rows) * maximum:
        raise ConfigurationError(
            f"{question.title}: las barras producen {selection_total} selecciones, pero los límites "
            f"requieren entre {len(rows) * minimum} y {len(rows) * maximum}."
        )
    if minimum and sum(count > 0 for count in targets.values()) < minimum:
        raise ConfigurationError(
            f"{question.title}: no hay suficientes opciones con respuestas para cumplir el mínimo."
        )

    selected_by_row = {row: [] for row in rows}
    degrees = {row: 0 for row in rows}
    option_order = list(targets)
    rng.shuffle(option_order)
    option_order.sort(key=lambda option: targets[option], reverse=True)
    for option in option_order:
        candidates = [row for row in rows if degrees[row] < maximum]
        rng.shuffle(candidates)
        candidates.sort(key=lambda row: degrees[row])
        chosen = candidates[: targets[option]]
        if len(chosen) != targets[option]:
            raise ConfigurationError(
                f"{question.title}: no es posible distribuir exactamente la opción {option} "
                "con los límites configurados."
            )
        for row in chosen:
            selected_by_row[row].append(option)
            degrees[row] += 1
    if any(degree < minimum for degree in degrees.values()):
        raise ConfigurationError(
            f"{question.title}: la combinación de cantidades y límites no tiene una distribución válida."
        )
    for row in rows:
        selected = selected_by_row[row]
        selected.sort(key=question.options.index)
        profiles[row]["answers"][question.id] = {"selected": selected}
    _attach_other_text(question, config, rows, profiles, rng)


def _attach_other_text(
    question: Question,
    config: dict[str, Any],
    rows: list[int],
    profiles: list[dict[str, Any]],
    rng: random.Random,
) -> None:
    other_rows = [
        row
        for row in rows
        if any(value.casefold().rstrip(":").strip() == "otro" for value in _selected(profiles[row]["answers"].get(question.id)))
    ]
    if not other_rows:
        return
    values = [str(value).strip() for value in config.get("other_values", []) if str(value).strip()]
    if len(values) < len(other_rows):
        raise ConfigurationError(
            f"{question.title}: se necesitan {len(other_rows)} textos para 'Otro' y solamente hay {len(values)}."
        )
    rng.shuffle(values)
    rng.shuffle(other_rows)
    for row, text in zip(other_rows, values, strict=False):
        profiles[row]["answers"][question.id]["other_text"] = text


def _assign_text(
    question: Question,
    config: dict[str, Any],
    rows: list[int],
    profiles: list[dict[str, Any]],
    rng: random.Random,
) -> None:
    values = [str(value).strip() for value in config.get("values", []) if str(value).strip()]
    if question.required and len(values) < len(rows):
        raise ConfigurationError(
            f"{question.title}: es obligatoria y requiere {len(rows)} textos; se proporcionaron {len(values)}."
        )
    rng.shuffle(values)
    rng.shuffle(rows)
    for position, row in enumerate(rows):
        profiles[row]["answers"][question.id] = {"text": values[position] if position < len(values) else ""}


def _assign(
    question: Question,
    config: dict[str, Any],
    rows: list[int],
    profiles: list[dict[str, Any]],
    rng: random.Random,
) -> None:
    if not rows:
        return
    if question.kind in ("single", "linear"):
        _assign_single(question, config, rows, profiles, rng)
    elif question.kind == "multiple":
        _assign_multiple(question, config, rows, profiles, rng)
    else:
        _assign_text(question, config, rows, profiles, rng)


def _rule_rows(
    rule: ConditionRule,
    profiles: list[dict[str, Any]],
) -> list[int]:
    return [
        row
        for row in range(len(profiles))
        if _matches(
            profiles[row]["answers"].get(rule.trigger_question_id),
            rule.trigger_values,
            rule.match_mode,
        )
    ]


def _residual_exclusive_config(
    question: Question,
    config: dict[str, Any],
    total_sample: int,
    remaining_total: int,
    reserved_options: set[str],
) -> dict[str, Any]:
    base = exclusive_counts(total_sample, config)
    candidates = [option for option in question.options if option not in reserved_options]
    if not question.required and UNANSWERED_KEY not in reserved_options:
        candidates.append(UNANSWERED_KEY)
    if remaining_total and not candidates:
        raise ConfigurationError(
            f"{question.title}: las condiciones reservaron todas las opciones, pero todavía "
            f"quedan {remaining_total} participantes sin respuesta. Modifique o elimine alguna condición."
        )
    if not remaining_total:
        return {"mode": "count", "counts": {option: 0 for option in question.options}}
    base_total = sum(base.get(option, 0) for option in candidates)
    if base_total <= 0:
        weights = {option: 100 / len(candidates) for option in candidates}
    else:
        weights = {
            option: 100 * base.get(option, 0) / base_total
            for option in candidates
        }
    weights[candidates[-1]] += 100 - sum(weights.values())
    allocated = largest_remainder(remaining_total, weights)
    residual = {
        "mode": "count",
        "counts": {
            option: allocated.get(option, 0)
            for option in question.options
        },
        "unanswered_count": allocated.get(UNANSWERED_KEY, 0),
        "other_values": list(config.get("other_values", [])),
    }
    return residual


def _assign_conditioned_exclusive(
    question: Question,
    config: dict[str, Any],
    rules: list[ConditionRule],
    profiles: list[dict[str, Any]],
    rng: random.Random,
) -> None:
    reservations: dict[int, str] = {}
    reservation_rule: dict[int, ConditionRule] = {}
    reserved_options: set[str] = set()
    distribution_rows: set[int] = set()

    force_rules = [rule for rule in rules if rule.action in ("force_answer", "unanswered")]
    distribution_rules = [rule for rule in rules if rule.action == "distribution"]
    for rule in force_rules:
        value = UNANSWERED_KEY if rule.action == "unanswered" else (rule.target_values[0] if rule.target_values else "")
        if value != UNANSWERED_KEY and value not in question.options:
            raise ConfigurationError(
                f"{question.title}: la condición {rule.id} intenta asignar una opción que ya no existe."
            )
        if value == UNANSWERED_KEY and question.required:
            raise ConfigurationError(
                f"{question.title}: una condición intenta dejar vacía una pregunta obligatoria."
            )
        applicable = _rule_rows(rule, profiles)
        for row in applicable:
            previous = reservations.get(row)
            if previous is not None and previous != value:
                previous_rule = reservation_rule[row]
                raise ConfigurationError(
                    f"{question.title}: las condiciones {previous_rule.id} y {rule.id} se contradicen "
                    f"para el participante {row + 1} ({previous} frente a {value}). "
                    "No es posible aumentar la muestra ni desplazar otra reserva; modifique las condiciones."
                )
            reservations[row] = value
            reservation_rule.setdefault(row, rule)
        reserved_options.add(value)

    for rule in distribution_rules:
        applicable = _rule_rows(rule, profiles)
        overlap = set(applicable) & (set(reservations) | distribution_rows)
        if overlap:
            raise ConfigurationError(
                f"{question.title}: la condición {rule.id} se superpone con otra reserva en "
                f"{len(overlap)} participantes. Reordene o modifique las condiciones."
            )
        _assign(question, rule.target_config, applicable, profiles, rng)
        distribution_rows.update(applicable)

    for row, value in reservations.items():
        profiles[row]["answers"][question.id] = {
            "selected": [] if value == UNANSWERED_KEY else [value]
        }

    remaining = [
        row
        for row in range(len(profiles))
        if row not in reservations and row not in distribution_rows
    ]
    residual = _residual_exclusive_config(
        question,
        config,
        len(profiles),
        len(remaining),
        reserved_options,
    )
    _assign_single(question, residual, remaining, profiles, rng)

    forced_other_rows = [
        row
        for row, value in reservations.items()
        if value.casefold().rstrip(":").strip() == "otro"
    ]
    if forced_other_rows:
        other_values: list[str] = []
        for rule in force_rules:
            other_values.extend(rule.target_config.get("other_values", []))
        _attach_other_text(
            question,
            {"other_values": other_values},
            forced_other_rows,
            profiles,
            rng,
        )


def _assign_conditioned_text(
    question: Question,
    config: dict[str, Any],
    rules: list[ConditionRule],
    profiles: list[dict[str, Any]],
    rng: random.Random,
) -> None:
    reservations: dict[int, str] = {}
    reservation_rule: dict[int, ConditionRule] = {}
    force_rules = [rule for rule in rules if rule.action in ("force_answer", "unanswered")]
    distribution_rules = [rule for rule in rules if rule.action == "distribution"]
    for rule in force_rules:
        value = "" if rule.action == "unanswered" else (rule.target_values[0] if rule.target_values else "")
        if question.required and not value:
            raise ConfigurationError(f"{question.title}: no puede quedar vacía porque es obligatoria.")
        for row in _rule_rows(rule, profiles):
            previous = reservations.get(row)
            if previous is not None and previous != value:
                raise ConfigurationError(
                    f"{question.title}: las condiciones {reservation_rule[row].id} y {rule.id} "
                    f"asignan textos diferentes al participante {row + 1}."
                )
            reservations[row] = value
            reservation_rule.setdefault(row, rule)
    for row, value in reservations.items():
        profiles[row]["answers"][question.id] = {"text": value}
    distribution_rows: set[int] = set()
    for rule in distribution_rules:
        applicable = _rule_rows(rule, profiles)
        overlap = set(applicable) & (set(reservations) | distribution_rows)
        if overlap:
            raise ConfigurationError(
                f"{question.title}: la condición {rule.id} se superpone con otra reserva "
                f"en {len(overlap)} participantes."
            )
        _assign_text(question, rule.target_config, applicable, profiles, rng)
        distribution_rows.update(applicable)
    remaining = [
        row
        for row in range(len(profiles))
        if row not in reservations and row not in distribution_rows
    ]
    _assign_text(question, config, remaining, profiles, rng)


def generate_responses(
    questions: list[Question],
    base_configs: dict[str, dict[str, Any]],
    conditions: list[ConditionRule],
    sample_size: int,
    seed: int,
) -> list[dict[str, Any]]:
    if sample_size <= 0:
        raise ConfigurationError("El tamaño de la muestra debe ser mayor que cero.")
    rng = random.Random(seed)
    profiles = [{"index": index + 1, "answers": {}} for index in range(sample_size)]
    by_id = {question.id: question for question in questions}
    target_rules: dict[str, list[ConditionRule]] = defaultdict(list)
    active_conditions = [rule for rule in conditions if rule.enabled]
    for rule in active_conditions:
        target_rules[rule.target_question_id].append(rule)

    for rules in target_rules.values():
        rules.sort(key=lambda rule: (rule.priority, rule.id))

    for question_id in _topological_order(questions, active_conditions):
        question = by_id[question_id]
        config = base_configs.get(question_id)
        if config is None:
            raise ConfigurationError(f"Falta configurar la pregunta: {question.title}")
        rules = target_rules.get(question_id, [])
        if rules and question.kind in ("single", "linear"):
            _assign_conditioned_exclusive(question, config, rules, profiles, rng)
        elif rules and question.kind in ("text", "paragraph"):
            _assign_conditioned_text(question, config, rules, profiles, rng)
        else:
            remaining = set(range(sample_size))
            for rule in rules:
                applicable = [row for row in _rule_rows(rule, profiles) if row in remaining]
                _assign(question, rule.target_config, applicable, profiles, rng)
                remaining.difference_update(applicable)
            _assign(question, config, sorted(remaining), profiles, rng)
    rng.shuffle(profiles)
    for index, profile in enumerate(profiles, start=1):
        profile["index"] = index
    return profiles


def summarize(questions: list[Question], profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total = len(profiles)
    for question in questions:
        counter: Counter[str] = Counter()
        answered = 0
        for profile in profiles:
            answer = profile["answers"].get(question.id, {})
            if "selected" in answer:
                values = answer["selected"]
                if values:
                    answered += 1
                counter.update(values)
            elif answer.get("text"):
                answered += 1
                counter["Con texto"] += 1
        if total - answered:
            counter["Sin respuesta"] = total - answered
        for option, count in counter.items():
            rows.append(
                {
                    "Pregunta": question.title[:90],
                    "Respuesta": option,
                    "Cantidad": count,
                    "Porcentaje": round(count * 100 / total, 2) if total else 0,
                }
            )
    return rows
