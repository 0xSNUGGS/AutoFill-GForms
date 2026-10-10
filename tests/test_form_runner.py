import unittest

from src.form_runner import FormAutomationError, _find_grid_option, normalize


class FakeRadio:
    def __init__(self, column, row):
        self.attributes = {
            "data-value": column,
            "aria-label": f"{column}, respuesta para {row}",
        }

    def get_attribute(self, name):
        return self.attributes.get(name)


class FakeLocator:
    def __init__(self, values):
        self.values = values

    def count(self):
        return len(self.values)

    def nth(self, index):
        return self.values[index]


class FakeBlock:
    def __init__(self, radios):
        self.radios = radios

    def locator(self, _selector):
        return FakeLocator(self.radios)


class FormRunnerTests(unittest.TestCase):
    def test_normalization_matches_google_titles(self):
        self.assertEqual(
            normalize("18. ¿Estaría dispuesto a registrar su vehículo? *"),
            "estaria dispuesto a registrar su vehiculo",
        )

    def test_grid_cell_matches_both_row_and_column(self):
        expected = FakeRadio("2 — Poco importante.", "Velocidad máxima.")
        block = FakeBlock(
            [
                FakeRadio("2 — Poco importante.", "Velocidad promedio."),
                expected,
                FakeRadio("3 — Moderadamente importante.", "Velocidad máxima."),
            ]
        )
        self.assertIs(
            _find_grid_option(block, "Velocidad máxima.", "2 — Poco importante."),
            expected,
        )

    def test_missing_grid_cell_is_reported(self):
        block = FakeBlock([FakeRadio("1", "Fila A")])
        with self.assertRaises(FormAutomationError):
            _find_grid_option(block, "Fila B", "1")


if __name__ == "__main__":
    unittest.main()

