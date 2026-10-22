@echo off
setlocal
cd /d "%~dp0"
title MK8DX Mod Manager

set "VENV=%~dp0.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "STAMP=%VENV%\requirements.installed"

if exist "%VPY%" goto :have_venv

rem ---- First run: find Python 3.9+ and create a private environment next to the app.
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto :make_venv
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto :make_venv

echo Python 3.9 or newer was not found.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
echo then run this file again.
goto :fail

:make_venv
echo Setting up the Mod Manager for the first time...
%PY% -m venv "%VENV%"
if errorlevel 1 goto :fail

:have_venv
rem ---- Install the libraries on first run, and again whenever requirements.txt changes.
fc /b requirements.txt "%STAMP%" >nul 2>nul
if not errorlevel 1 goto :check_7zip
echo Installing required libraries (needs an internet connection)...
"%VPY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :fail
copy /y requirements.txt "%STAMP%" >nul

:check_7zip
rem ---- Not required to start, but .rar / .7z mods can't be unpacked without it.
set "SZ1=%ProgramFiles%\7-Zip\7z.exe"
set "SZ2=%ProgramFiles(x86)%\7-Zip\7z.exe"
if exist "%SZ1%" goto :run
if exist "%SZ2%" goto :run
where 7z >nul 2>nul
if not errorlevel 1 goto :run
echo.
echo Note: 7-Zip was not found. Mods packed as .rar or .7z can't be unpacked without it.
echo Get it from https://www.7-zip.org/ - the app still starts without it.
echo.

:run
"%VPY%" src\mod_manager.py
if errorlevel 1 goto :fail
endlocal
exit /b 0

:fail
echo.
echo The Mod Manager could not start. The messages above say why.
pause
endlocal
exit /b 1
