import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class LegacyQuestion:
    """Question shape kept by a Streamlit session from an older app version."""

    def to_dict(self):
        return {
            "id": "legacy-scale",
            "number": 1,
            "title": "¿Qué tan fácil?",
            "kind": "linear",
            "required": True,
            "options": ["1", "2", "3", "4", "5"],
            "section": "General",
        }


class AppSmokeTests(unittest.TestCase):
    def test_initial_screen_renders_without_exceptions(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        app.run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "FormsScript")

    def test_sample_size_is_available_before_pdf_and_updates_granularity(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        app.run(timeout=20)
        self.assertEqual(app.number_input[0].label, "Tamaño de la muestra")
        app.number_input[0].set_value(30)
        app.run(timeout=20)
        self.assertFalse(app.exception)
        self.assertTrue(any("3,33%" in caption.value for caption in app.caption))

    def test_question_editor_renders_with_count_mode_data(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        app.run(timeout=20)
        app.session_state["questions"] = [
            {
                "id": "q1",
                "number": 1,
                "title": "¿Dónde vive?",
                "kind": "single",
                "required": True,
                "options": ["Ciudad", "Otro:"],
                "section": "General",
            }
        ]
        app.session_state["configs"] = {
            "q1": {
                "mode": "percentage",
                "weights": {"Ciudad": 80.0, "Otro:": 20.0},
                "counts": {"Ciudad": 160, "Otro:": 40},
                "other_values": [],
            }
        }
        app.run(timeout=20)
        self.assertFalse(app.exception)
        captions = [caption.value for caption in app.caption]
        self.assertTrue(any("40 necesarios" in value for value in captions))

    def test_generated_preview_renders_without_pyarrow_dataframe(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        app.run(timeout=20)
        app.number_input[0].set_value(10)
        app.session_state["questions"] = [
            {
                "id": "q1",
                "number": 1,
                "title": "¿Resultado?",
                "kind": "single",
                "required": True,
                "options": ["Sí", "No"],
                "section": "General",
            }
        ]
        app.session_state["configs"] = {
            "q1": {
                "mode": "count",
                "counts": {"Sí": 6, "No": 4},
                "weights": {"Sí": 60.0, "No": 40.0},
                "basis_total": 10,
                "other_values": [],
            }
        }
        app.run(timeout=20)
        generate = next(button for button in app.button if button.label == "Generar vista previa")
        generate.click()
        app.run(timeout=20)
        self.assertFalse(app.exception)
        self.assertTrue(any("exactamente 10 respuestas" in item.value for item in app.success))

    def test_grid_question_editor_and_generation_render(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        app.run(timeout=20)
        app.number_input[0].set_value(10)
        app.session_state["questions"] = [
            {
                "id": "q1",
                "number": 1,
                "title": "Valore cada métrica",
                "kind": "grid",
                "required": True,
                "options": ["1 — Bajo", "2 — Alto"],
                "rows": ["Velocidad", "Resistencia"],
                "section": "General",
            }
        ]
        app.session_state["configs"] = {
            "q1": {
                "row_configs": {
                    "Velocidad": {"mode": "count", "counts": {"1 — Bajo": 4, "2 — Alto": 6}, "basis_total": 10},
                    "Resistencia": {"mode": "count", "counts": {"1 — Bajo": 7, "2 — Alto": 3}, "basis_total": 10},
                }
            }
        }
        app.run(timeout=20)
        self.assertFalse(app.exception)
        self.assertTrue(any(field.label == "Filas, una por línea" for field in app.text_area))
        generate = next(button for button in app.button if button.label == "Generar vista previa")
        generate.click()
        app.run(timeout=20)
        self.assertFalse(app.exception)
        self.assertTrue(any("exactamente 10 respuestas" in item.value for item in app.success))

    def test_legacy_question_session_is_migrated_on_reload(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        app.run(timeout=20)
        app.session_state["questions"] = [LegacyQuestion()]
        app.session_state["configs"] = {
            "legacy-scale": {
                "mode": "count",
                "counts": {str(value): 40 for value in range(1, 6)},
                "weights": {str(value): 20.0 for value in range(1, 6)},
                "basis_total": 200,
                "other_values": [],
            }
        }
        app.run(timeout=20)
        self.assertFalse(app.exception)
        self.assertTrue(any(field.label == "Significado de 1" for field in app.text_input))

    def test_inline_condition_can_be_created_from_source_question(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        app.run(timeout=20)
        app.session_state["questions"] = [
            {
                "id": "q1",
                "number": 1,
                "title": "Origen",
                "kind": "single",
                "required": True,
                "options": ["Sí", "No"],
                "section": "General",
            },
            {
                "id": "q2",
                "number": 2,
                "title": "Destino",
                "kind": "single",
                "required": True,
                "options": ["A", "B"],
                "section": "General",
            },
        ]
        app.session_state["configs"] = {
            "q1": {"mode": "count", "counts": {"Sí": 100, "No": 100}, "basis_total": 200},
            "q2": {"mode": "count", "counts": {"A": 100, "B": 100}, "basis_total": 200},
        }
        app.run(timeout=20)
        condition_toggle = next(item for item in app.checkbox if item.label == "Condicionar opciones")
        condition_toggle.set_value(True)
        app.run(timeout=20)
        add_button = next(item for item in app.button if item.label == "Agregar condición")
        add_button.click()
        app.run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state["conditions"]), 1)
        rule = app.session_state["conditions"][0]
        self.assertEqual(rule["trigger_question_id"], "q1")
        self.assertEqual(rule["target_question_id"], "q2")
        self.assertEqual(rule["action"], "force_answer")


if __name__ == "__main__":
    unittest.main()
