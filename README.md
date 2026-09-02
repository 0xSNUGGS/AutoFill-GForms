# FormsScript

Aplicación local para diseñar distribuciones de respuestas, generar muestras
exactas y completar formularios propios de Google Forms destinados a pruebas.
La interfaz funciona en el navegador mediante Streamlit y la automatización usa
Chromium mediante Playwright.

> Use FormsScript únicamente con formularios propios o para los que tenga
> autorización. La aplicación no evade CAPTCHA, autenticación ni límites de
> Google.

## Funciones principales

- Interpreta preguntas desde una exportación PDF de Google Forms.
- Detecta selección única, selección múltiple, escalas y texto libre.
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
- Un enlace público para responder el formulario y su exportación en PDF.

Al instalar Python en otra computadora, active la opción **Add Python to PATH**.
No es necesario instalar Google Chrome: Playwright descarga su propio Chromium.

## Instalación

Clone o descargue este repositorio y abra PowerShell en su carpeta raíz. No copie
`.venv` desde otra ubicación ni lo suba a Git; debe reconstruirse en cada equipo.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Si `py` no está disponible pero `python` sí, use `python -m venv .venv` en el
primer comando. Los demás comandos no cambian.

## Ejecución

Después de completar la instalación, puede hacer doble clic en
`FormsScript.exe`. La ventana que se abre debe permanecer abierta mientras usa
la aplicación. Streamlit abrirá normalmente `http://localhost:8501`; presione
`Ctrl+C` en la ventana para detener el servidor.

También puede iniciarla directamente desde PowerShell:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

`FormsScript.exe` es un lanzador para Windows, no una distribución autónoma:
debe permanecer en la raíz, junto a `app.py`, y necesita el entorno `.venv`
instalado siguiendo los pasos anteriores. Esto evita incluir una segunda copia
de Python y permite actualizar las dependencias y Chromium normalmente.

## Flujo recomendado

1. Defina el tamaño de la muestra antes de analizar el formulario.
2. En Google Forms, abra **Enviar** y copie el enlace para responder.
3. Desde la vista de impresión, exporte el formulario a PDF.
4. Cargue en FormsScript el enlace y el PDF.
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
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
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
src/pdf_parser.py         Interpretación de la exportación PDF
src/generator.py          Generación y validación de respuestas
src/form_runner.py        Automatización del formulario con Playwright
src/authorization.py      Autorización local de enlaces
src/run_store.py          Registro local de ejecuciones
tests/                    Pruebas automatizadas
launcher/                 Código fuente del lanzador para Windows
requirements.txt          Dependencias de Python
```

## Limitaciones

- El PDF no contiene los identificadores internos de Google Forms; las preguntas
  se asocian comparando sus títulos visibles. Revise siempre la estructura.
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
