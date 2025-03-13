# Setup script for windows

if (-not (Test-Path .\venv)) {
    python -m venv venv
}

.\venv\Scripts\activate.ps1
pip install -r requirements.txt