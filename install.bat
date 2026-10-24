:: install.bat
@echo off
setlocal

echo Creating virtual environment...
python -m venv .venv

.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install pywin32

if not exist config.json (
    echo Creating default config...
    .venv\Scripts\python -c "from config import DEFAULT_CONFIG; import json; json.dump(DEFAULT_CONFIG, open('config.json','w'), indent=2)"
)

echo Installing service...
.venv\Scripts\python install_service.py --os windows

endlocal
pause
