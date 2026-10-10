import unittest

from src.form_parser import parse_google_form_data


class FormParserTests(unittest.TestCase):
    def test_grid_rows_and_columns_are_recognized(self):
        data = [
            None,
            [
                None,
                [
                    [10, "Métricas", "Descripción", 8, None],
                    [
                        20,
                        "Valore cada métrica",
                        None,
                        7,
                        [
                            [101, [["1 — Bajo"], ["2 — Alto"]], 1, ["Velocidad"]],
                            [102, [["1 — Bajo"], ["2 — Alto"]], 1, ["Resistencia"]],
                        ],
                    ],
                ],
            ],
        ]

        questions = parse_google_form_data(data)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].kind, "grid")
        self.assertEqual(questions[0].section, "Métricas")
        self.assertEqual(questions[0].options, ["1 — Bajo", "2 — Alto"])
        self.assertEqual(questions[0].rows, ["Velocidad", "Resistencia"])
        self.assertTrue(questions[0].required)

    def test_other_option_is_preserved(self):
        data = [None, [None, [[1, "Herramienta", None, 2, [[2, [["Excel", None, None, None, 0], ["", None, None, None, 1]], 0]]]]]]
        questions = parse_google_form_data(data)
        self.assertEqual(questions[0].options, ["Excel", "Otro:"])


if __name__ == "__main__":
    unittest.main()
