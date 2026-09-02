using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;

internal static class FormsScriptLauncher
{
    private static int Main()
    {
        Console.OutputEncoding = Encoding.UTF8;

        string executable = Assembly.GetExecutingAssembly().Location;
        string projectDirectory = Path.GetDirectoryName(executable);
        string python = Path.Combine(projectDirectory, ".venv", "Scripts", "python.exe");
        string application = Path.Combine(projectDirectory, "app.py");

        if (!File.Exists(application))
        {
            return Fail("No se encontró app.py junto a FormsScript.exe.");
        }

        if (!File.Exists(python))
        {
            return Fail(
                "No se encontró el entorno virtual .venv.\n\n" +
                "Abra PowerShell en esta carpeta y ejecute:\n" +
                "  py -m venv .venv\n" +
                "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt\n" +
                "  .\\.venv\\Scripts\\python.exe -m playwright install chromium"
            );
        }

        try
        {
            Console.WriteLine("Iniciando FormsScript...");
            Console.WriteLine("Mantenga esta ventana abierta mientras use la aplicación.");
            Console.WriteLine("Presione Ctrl+C para detenerla.\n");

            var startInfo = new ProcessStartInfo
            {
                FileName = python,
                Arguments = "-m streamlit run " + Quote(application),
                WorkingDirectory = projectDirectory,
                UseShellExecute = false
            };

            using (Process process = Process.Start(startInfo))
            {
                process.WaitForExit();
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            return Fail("No se pudo iniciar FormsScript.\n\n" + error.Message);
        }
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    private static int Fail(string message)
    {
        Console.Error.WriteLine("FormsScript\n");
        Console.Error.WriteLine(message);
        Console.Error.WriteLine("\nConsulte README.md para ver la instalación completa.");
        Console.Error.WriteLine("Presione una tecla para cerrar...");
        Console.ReadKey(true);
        return 1;
    }
}
