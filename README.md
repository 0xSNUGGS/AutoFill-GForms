# FormsScript

Aplicación local para diseñar distribuciones de respuestas, generar muestras
exactas y completar formularios propios de Google Forms destinados a pruebas.
La interfaz funciona en el navegador mediante Streamlit y la automatización usa
Chromium mediante Playwright.

> Use FormsScript únicamente con formularios propios o para los que tenga
> autorización. La aplicación no evade CAPTCHA, autenticación ni límites de
> Google.

## Funciones principales

- Interpreta preguntas directamente desde un enlace público o de edición de
  Google Forms; el PDF puede adjuntarse como referencia visual.
- Detecta selección única, selección múltiple, escalas, cuadrículas de opción
  múltiple y texto libre.
- Permite revisar y corregir la estructura detectada antes de generar datos.
- Genera un número exacto de respuestas, sin fracciones de participantes.
- Configura distribuciones mediante gráficos, porcentajes o cantidades.
- Admite respuestas `Otro`, preguntas opcionales y textos separados por `;` o
  saltos de línea.
- Aplica condiciones entre preguntas, reservas exactas y validación de
  dependencias circulares o contradictorias.
- Previsualiza y exporta respuestas en JSON y CSV.
- Valida una respuesta sin enviarla y luego permite ejecutar el lote completo.
- Guarda cada intento localmente y permite reintentar solo los fallos.
- Detiene la automatización si aparece un CAPTCHA.

## Requisitos

- Windows 10 u 11 de 64 bits.
- Python de 64 bits, preferentemente Python 3.11 o posterior.
- Acceso a Internet durante la instalación de dependencias y Chromium.
- Un enlace público o de edición del formulario. El PDF es opcional si analiza
  directamente el enlace.

Al instalar Python en otra computadora, active la opción **Add Python to PATH**.
No es necesario instalar Google Chrome: Playwright descarga su propio Chromium.

## Instalación

Clone o descargue este repositorio y abra PowerShell en su carpeta raíz. No copie
`.venv` desde otra ubicación ni lo suba a Git; debe reconstruirse en cada equipo.

```powershell
py -m venv .venv
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py -m playwright install chromium
```

Si `py` no está disponible pero `python` sí, use `python -m venv .venv`

## Ejecución

Después de completar la instalación, puede hacer doble clic en
`FormsScript.exe`. La ventana que se abre debe permanecer abierta mientras usa
la aplicación. Streamlit abrirá normalmente `http://localhost:8501`; presione
`Ctrl+C` en la ventana para detener el servidor.

También puede iniciarla directamente desde PowerShell:

```powershell
py -m streamlit run app.py
```

`FormsScript.exe` es un lanzador para Windows, no una distribución autónoma:
debe permanecer en la raíz, junto a `app.py`, y necesita el entorno `.venv`
instalado siguiendo los pasos anteriores. Esto evita incluir una segunda copia
de Python y permite actualizar las dependencias y Chromium normalmente.

## Flujo recomendado

1. Defina el tamaño de la muestra antes de analizar el formulario.
2. En Google Forms, abra **Enviar** y copie el enlace para responder.
3. Opcionalmente, exporte el formulario a PDF desde la vista de impresión.
4. Pegue el enlace y pulse **Analizar formulario**. Adjunte el PDF si desea una
   referencia visual dentro de FormsScript.
5. Revise las preguntas y corrija cualquier interpretación incorrecta.
6. Configure distribuciones, textos y condiciones.
7. Genere la vista previa y revise el resumen.
8. Autorice localmente el enlace del formulario de pruebas.
9. Ejecute **Validar primera respuesta sin enviar**.
10. Confirme el envío completo solamente si la validación es correcta.

> Es recomendado que desactive la opción: "Recopilar direcciones de
> correo electrónico", localizado en las configuraciones del
> formulario

## Distribuciones y granularidad

En selección única y escalas, la distribución siempre suma el tamaño completo
de la muestra. Las cantidades enteras son la fuente de verdad. Por ejemplo, en
una muestra de 30 personas el paso mínimo es una respuesta, aproximadamente
`3,33 %`; nunca se conserva un porcentaje que represente una fracción de una
persona. Si cambia la muestra, la distribución se vuelve a escalar.

En selección múltiple, cada opción representa una tasa de selección
independiente. Por eso la suma puede superar el 100 %. El generador valida que
las cantidades sean compatibles con los límites mínimo y máximo de selecciones
por participante.

En una cuadrícula de opción múltiple, cada fila tiene su propia distribución
exclusiva entre las columnas disponibles. FormsScript conserva cantidades
exactas por fila, las resume y exporta por separado, y selecciona la celda
correspondiente durante la automatización.

## Condiciones

Una respuesta puede fijar otra respuesta posterior, dejar vacía una pregunta
opcional o aplicar una distribución especial. Las reservas condicionadas forman
parte de la muestra original; no crean participantes adicionales. Las reservas
compatibles se combinan y las contradicciones o dependencias circulares detienen
la generación con un mensaje de error.

## Datos locales y privacidad

- `data/authorized_forms.json` guarda los formularios aprobados localmente.
- `data/runs/*.jsonl` guarda el resultado de cada intento.
- `tmp/` puede contener archivos temporales.
- `.streamlit/secrets.toml`, si se crea, puede contener configuración privada.

Estas rutas, `.venv`, los archivos `*.pyc` y `__pycache__` están excluidos por
`.gitignore` y no deben subirse a GitHub. Los archivos generados en `data/`
pueden contener respuestas; trátelos como información privada.

## Pruebas

Para ejecutar todas las pruebas automatizadas:

```powershell
py -m unittest discover -s tests -v
```

## Reconstruir el ejecutable

El repositorio incluye el código del lanzador en
`launcher/FormsScriptLauncher.cs`. En Windows, ejecute:

```powershell
.\build-launcher.cmd
```

El script utiliza el compilador de C# de .NET Framework incluido en Windows y
reemplaza `FormsScript.exe` en la raíz.

## Estructura

```text
app.py                    Interfaz y flujo principal de Streamlit
components/               Editor gráfico de distribuciones
src/form_parser.py        Análisis de la estructura pública de Google Forms
src/pdf_parser.py         Interpretación alternativa de la exportación PDF
src/generator.py          Generación y validación de respuestas
src/form_runner.py        Automatización del formulario con Playwright
src/authorization.py      Autorización local de enlaces
src/run_store.py          Registro local de ejecuciones
tests/                    Pruebas automatizadas
launcher/                 Código fuente del lanzador para Windows
requirements.txt          Dependencias de Python
```

## Limitaciones

- Durante el envío, las preguntas se asocian comparando sus títulos visibles y
  las cuadrículas comparan tanto el nombre de la fila como el de la columna.
  Revise siempre la estructura detectada.
- Algunos PDF exportados son imágenes sin capa de texto. En esos casos use
  **Analizar formulario**; el PDF seguirá disponible como referencia visual.
- No se admiten cargas de archivos ni preguntas que exijan iniciar sesión.
- Un cambio en la interfaz de Google Forms puede requerir actualizar los
  selectores de Playwright.
- La computadora debe permanecer encendida y conectada mientras se ejecuta un
  lote.

## Solución de problemas

- **No se encontró `.venv`:** repita los comandos de la sección Instalación.
- **No abre Chromium:** ejecute nuevamente
  `.\.venv\Scripts\python.exe -m playwright install chromium`.
- **El puerto 8501 está ocupado:** cierre la instancia anterior o ejecute
  `.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8502`.
- **Google muestra CAPTCHA:** detenga el lote y complételo manualmente; la
  aplicación no intenta evitarlo.
