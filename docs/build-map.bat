@echo off
REM Regenera figura-4-ubicacion.png (mapa de ubicación del informe).
REM   build-map.bat                      coordenadas desde el JSON del caso
REM   build-map.bat 7.780639 -72.221870  coordenadas explícitas
cd /d "%~dp0"
python build-map.py %*
echo.
pause
