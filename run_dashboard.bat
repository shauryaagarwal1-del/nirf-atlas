@echo off
REM Start the NIRF Atlas dashboard on Windows: double-click this file.
REM It activates the project's virtual environment (.venv) and runs Streamlit on app/Home.py,
REM which opens at http://localhost:8501. Close this window (or press Ctrl+C) to stop the app.

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo The virtual environment .venv was not found in %CD%.
    echo Follow the Setup steps in README.md first, then double-click this file again.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
echo Starting NIRF Atlas at http://localhost:8501 ...
echo The Ask NIRF chat needs internet (Gemini API); every other page works offline.
python -m streamlit run app/Home.py
pause
