@echo off
REM Regenera los PDF de la carpeta docs/ (instructivo + informe).
REM Doble clic para ejecutar, o desde consola: build-pdf.bat
cd /d "%~dp0"
python build-pdf.py %*
echo.
pause
