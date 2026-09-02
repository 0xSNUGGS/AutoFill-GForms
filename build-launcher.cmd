@echo off
setlocal

set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"

if not exist "%CSC%" (
    echo No se encontro el compilador de C# incluido con .NET Framework.
    exit /b 1
)

"%CSC%" /nologo /target:exe /optimize+ /out:"%~dp0FormsScript.exe" "%~dp0launcher\FormsScriptLauncher.cs"
if errorlevel 1 exit /b 1

echo FormsScript.exe creado correctamente.
