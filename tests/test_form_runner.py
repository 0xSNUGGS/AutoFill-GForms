import unittest

from src.form_runner import normalize


class FormRunnerTests(unittest.TestCase):
    def test_normalization_matches_google_titles(self):
        self.assertEqual(
            normalize("18. ¿Estaría dispuesto a registrar su vehículo? *"),
            "estaria dispuesto a registrar su vehiculo",
        )


if __name__ == "__main__":
    unittest.main()

