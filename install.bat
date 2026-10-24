:: install.bat
@echo off
setlocal

echo Creating virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo ERROR: failed to create .venv. Is Python 3.10+ on PATH?
    exit /b 1
)

.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed. See output above.
    exit /b 1
)
.venv\Scripts\pip install pywin32
if errorlevel 1 (
    echo ERROR: pywin32 install failed.
    exit /b 1
)

if not exist config.json (
    echo Creating default config...
    .venv\Scripts\python -c "from config import DEFAULT_CONFIG; import json; json.dump(DEFAULT_CONFIG, open('config.json','w'), indent=2)"
    if errorlevel 1 (
        echo ERROR: config creation failed.
        exit /b 1
    )
)

echo Installing service...
.venv\Scripts\python install_service.py --os windows
if errorlevel 1 (
    echo ERROR: service installation failed.
    exit /b 1
)

endlocal
pause
