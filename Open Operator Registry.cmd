@echo off
cd /d "%~dp0"
set "REGISTRY_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%REGISTRY_PY%" (
  start "" "%REGISTRY_PY%" "%~dp0operator_registry.py"
) else (
  pyw -3 "%~dp0operator_registry.py"
  if errorlevel 1 (
    echo Python 3 with Tkinter is required on this computer.
    pause
  )
)
