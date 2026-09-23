@echo off
cd /d "%~dp0"
set MK8DX_DEBUG=1
python src\mod_manager.py
