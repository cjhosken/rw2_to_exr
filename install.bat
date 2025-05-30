
set "SCRIPT_DIR=%~dp0"
cd %SCRIPT_DIR%
python -m venv .venv

call .\.venv\Scripts\activate.bat

python -m pip install --upgrade pip

python -m pip install -r .\requirements.txt 

python -m PyInstaller --windowed --onefile ./rw2toexr.py