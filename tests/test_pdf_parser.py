import io
import unittest
from unittest.mock import patch

from src.pdf_parser import parse_google_forms_pdf


SAMPLE_TEXT = """
30/8/26, 20:38 Encuesta de prueba
Sección A. Hábitos
1. 1. ¿Con qué frecuencia compra? *
Marca solo un óvalo.
Siempre.
A veces.
Nunca.
2. 2. ¿Dónde compra? *
Selecciona todos los que correspondan.
Stock
Biggie
Otro:
3. 3. ¿Qué tan fácil resulta *
usar esto?
Marca solo un óvalo.
1  2  3  4  5
Muy difícil          Muy fácil
4. 4. Comentario adicional (Opcional)
https://docs.google.com/forms/d/example/edit
1/1
"""


class FakePage:
    def extract_text(self, **_kwargs):
        return SAMPLE_TEXT


class FakeDocument:
    pages = [FakePage()]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class PdfParserTests(unittest.TestCase):
    @patch("src.pdf_parser.pdfplumber.open", return_value=FakeDocument())
    def test_google_forms_export_is_recognized(self, _open):
        questions = parse_google_forms_pdf(io.BytesIO(b"fake"))
        self.assertEqual(len(questions), 4)
        self.assertEqual(questions[0].kind, "single")
        self.assertEqual(questions[0].options, ["Siempre.", "A veces.", "Nunca."])
        self.assertEqual(questions[1].kind, "multiple")
        self.assertEqual(questions[1].options[-1], "Otro:")
        self.assertEqual(questions[2].kind, "linear")
        self.assertEqual(questions[2].title, "¿Qué tan fácil resulta usar esto?")
        self.assertEqual(questions[2].options, ["1", "2", "3", "4", "5"])
        self.assertEqual(questions[2].scale_min_label, "Muy difícil")
        self.assertEqual(questions[2].scale_max_label, "Muy fácil")
        self.assertEqual(questions[3].kind, "paragraph")
        self.assertFalse(questions[3].required)


if __name__ == "__main__":
    unittest.main()
