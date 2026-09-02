import unittest

from src.generator import ConfigurationError, generate_responses, largest_remainder, planned_option_count
from src.models import ConditionRule, Question


class GeneratorTests(unittest.TestCase):
    def test_largest_remainder_is_exact(self):
        counts = largest_remainder(200, {"A": 20, "B": 40, "C": 15, "D": 15, "E": 10})
        self.assertEqual(counts, {"A": 40, "B": 80, "C": 30, "D": 30, "E": 20})
        self.assertEqual(sum(counts.values()), 200)

    def test_condition_overrides_target_distribution(self):
        questions = [
            Question("q1", 1, "¿Posee vehículo?", "single", True, ["Sí", "No"]),
            Question("q2", 2, "¿Registraría su vehículo?", "single", True, ["Sí", "No"]),
        ]
        configs = {
            "q1": {"weights": {"Sí": 80, "No": 20}, "other_values": []},
            "q2": {"weights": {"Sí": 100, "No": 0}, "other_values": []},
        }
        conditions = [
            ConditionRule(
                "rule1",
                "q1",
                ["No"],
                "q2",
                {"weights": {"Sí": 0, "No": 100}, "other_values": []},
            )
        ]
        profiles = generate_responses(questions, configs, conditions, 200, 1234)
        no_vehicle = [profile for profile in profiles if profile["answers"]["q1"]["selected"] == ["No"]]
        self.assertEqual(len(no_vehicle), 40)
        self.assertTrue(all(profile["answers"]["q2"]["selected"] == ["No"] for profile in no_vehicle))

    def test_forced_options_reserve_population_and_adjust_only_unaffected_options(self):
        questions = [
            Question("q1", 1, "Grupo", "single", True, ["Grupo C", "Grupo D", "Resto"]),
            Question("q2", 2, "Destino", "single", True, ["A", "B", "C", "D"]),
        ]
        configs = {
            "q1": {
                "mode": "count",
                "counts": {"Grupo C": 50, "Grupo D": 50, "Resto": 100},
            },
            "q2": {
                "mode": "count",
                "counts": {"A": 80, "B": 40, "C": 40, "D": 40},
            },
        }
        conditions = [
            ConditionRule(
                id="force-c",
                trigger_question_id="q1",
                trigger_values=["Grupo C"],
                target_question_id="q2",
                target_config={},
                action="force_answer",
                target_values=["C"],
            ),
            ConditionRule(
                id="force-d",
                trigger_question_id="q1",
                trigger_values=["Grupo D"],
                target_question_id="q2",
                target_config={},
                action="force_answer",
                target_values=["D"],
            ),
        ]
        profiles = generate_responses(questions, configs, conditions, 200, 31)
        target = [profile["answers"]["q2"]["selected"][0] for profile in profiles]
        self.assertEqual(len(profiles), 200)
        self.assertEqual(target.count("C"), 50)
        self.assertEqual(target.count("D"), 50)
        self.assertEqual(target.count("A"), 67)
        self.assertEqual(target.count("B"), 33)
        for profile in profiles:
            source_value = profile["answers"]["q1"]["selected"][0]
            target_value = profile["answers"]["q2"]["selected"][0]
            if source_value == "Grupo C":
                self.assertEqual(target_value, "C")
            elif source_value == "Grupo D":
                self.assertEqual(target_value, "D")

    def test_contradictory_reservations_over_sample_are_rejected(self):
        questions = [
            Question("q1", 1, "Origen 1", "single", True, ["Sí", "No"]),
            Question("q2", 2, "Origen 2", "single", True, ["Sí", "No"]),
            Question("q3", 3, "Destino", "single", True, ["A", "B", "C"]),
        ]
        configs = {
            "q1": {"mode": "count", "counts": {"Sí": 100, "No": 100}},
            "q2": {"mode": "count", "counts": {"Sí": 150, "No": 50}},
            "q3": {"mode": "count", "counts": {"A": 70, "B": 70, "C": 60}},
        }
        conditions = [
            ConditionRule(
                id="reserve-a",
                trigger_question_id="q1",
                trigger_values=["Sí"],
                target_question_id="q3",
                target_config={},
                action="force_answer",
                target_values=["A"],
            ),
            ConditionRule(
                id="reserve-b",
                trigger_question_id="q2",
                trigger_values=["Sí"],
                target_question_id="q3",
                target_config={},
                action="force_answer",
                target_values=["B"],
            ),
        ]
        with self.assertRaisesRegex(ConfigurationError, "No es posible aumentar la muestra"):
            generate_responses(questions, configs, conditions, 200, 13)

    def test_exclusive_quantities_are_exact(self):
        questions = [Question("q1", 1, "Opción", "single", True, ["A", "B", "Otro:"])]
        config = {
            "q1": {
                "mode": "count",
                "counts": {"A": 100, "B": 80, "Otro:": 20},
                "weights": {"A": 0, "B": 0, "Otro:": 0},
                "other_values": [f"Texto {index}" for index in range(20)],
            }
        }
        profiles = generate_responses(questions, config, [], 200, 22)
        selected = [profile["answers"]["q1"]["selected"][0] for profile in profiles]
        self.assertEqual(selected.count("A"), 100)
        self.assertEqual(selected.count("B"), 80)
        self.assertEqual(selected.count("Otro:"), 20)
        self.assertEqual(planned_option_count(200, config["q1"], "Otro:"), 20)

    def test_multiple_quantities_are_independent(self):
        questions = [Question("q1", 1, "Lugares", "multiple", True, ["A", "B"])]
        config = {
            "q1": {
                "mode": "count",
                "counts": {"A": 80, "B": 40},
                "weights": {"A": 0, "B": 0},
                "minimum": 0,
                "maximum": 2,
            }
        }
        profiles = generate_responses(questions, config, [], 100, 55)
        selected_a = sum("A" in profile["answers"]["q1"]["selected"] for profile in profiles)
        selected_b = sum("B" in profile["answers"]["q1"]["selected"] for profile in profiles)
        self.assertEqual(selected_a, 80)
        self.assertEqual(selected_b, 40)

    def test_multiple_quantities_respect_exact_limits(self):
        questions = [Question("q1", 1, "Canales", "multiple", True, ["A", "B", "C"])]
        config = {
            "q1": {
                "mode": "count",
                "counts": {"A": 8, "B": 7, "C": 5},
                "minimum": 2,
                "maximum": 2,
            }
        }
        profiles = generate_responses(questions, config, [], 10, 91)
        answers = [profile["answers"]["q1"]["selected"] for profile in profiles]
        self.assertTrue(all(len(selected) == 2 for selected in answers))
        self.assertEqual(sum("A" in selected for selected in answers), 8)
        self.assertEqual(sum("B" in selected for selected in answers), 7)
        self.assertEqual(sum("C" in selected for selected in answers), 5)

    def test_impossible_multiple_limits_are_rejected(self):
        questions = [Question("q1", 1, "Canales", "multiple", True, ["A", "B"])]
        config = {
            "q1": {
                "mode": "count",
                "counts": {"A": 2, "B": 2},
                "minimum": 1,
                "maximum": 2,
            }
        }
        with self.assertRaises(ConfigurationError):
            generate_responses(questions, config, [], 10, 5)

    def test_optional_exclusive_question_can_be_unanswered(self):
        questions = [Question("q1", 1, "Opcional", "single", False, ["Sí", "No"])]
        config = {
            "q1": {
                "mode": "count",
                "counts": {"Sí": 4, "No": 3},
                "unanswered_count": 3,
            }
        }
        profiles = generate_responses(questions, config, [], 10, 17)
        answers = [profile["answers"]["q1"]["selected"] for profile in profiles]
        self.assertEqual(sum(not selected for selected in answers), 3)
        self.assertEqual(sum(selected == ["Sí"] for selected in answers), 4)
        self.assertEqual(sum(selected == ["No"] for selected in answers), 3)

    def test_other_text_is_used_once(self):
        questions = [Question("q1", 1, "Lugar", "single", True, ["A", "Otro:"])]
        config = {
            "q1": {
                "weights": {"A": 50, "Otro:": 50},
                "other_values": ["Uno", "Dos"],
            }
        }
        profiles = generate_responses(questions, config, [], 4, 8)
        texts = sorted(
            profile["answers"]["q1"].get("other_text")
            for profile in profiles
            if profile["answers"]["q1"]["selected"] == ["Otro:"]
        )
        self.assertEqual(texts, ["Dos", "Uno"])

    def test_cycle_is_rejected(self):
        questions = [
            Question("q1", 1, "A", "single", True, ["Sí"]),
            Question("q2", 2, "B", "single", True, ["Sí"]),
        ]
        configs = {
            "q1": {"weights": {"Sí": 100}},
            "q2": {"weights": {"Sí": 100}},
        }
        rules = [
            ConditionRule("a", "q1", ["Sí"], "q2", configs["q2"]),
            ConditionRule("b", "q2", ["Sí"], "q1", configs["q1"]),
        ]
        with self.assertRaises(ConfigurationError):
            generate_responses(questions, configs, rules, 1, 1)


if __name__ == "__main__":
    unittest.main()
