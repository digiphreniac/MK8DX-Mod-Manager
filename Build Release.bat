@echo off
rem Builds the downloadable Windows release (dist\MK8DX-Mod-Manager-v<version>-windows.zip).
rem Needs Python on PATH and 7-Zip installed; see tools\build_release.py.
cd /d "%~dp0"
python tools\build_release.py %*
if errorlevel 1 (
    echo.
    echo The build failed. The messages above say why.
)
pause
