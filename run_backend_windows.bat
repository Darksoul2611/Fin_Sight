@echo off
cd /d "%~dp0backend"
if not exist .venv (py -m venv .venv)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
set SECRET_KEY=development-only-change-this-before-deploying
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pause
