#!/usr/bin/env bash
# Start the NIRF Atlas dashboard on macOS / Linux: run ./run_dashboard.sh from a terminal.
# It activates the project's virtual environment (.venv) and runs Streamlit on app/Home.py,
# which opens at http://localhost:8501. Press Ctrl+C to stop the app.

set -e
cd "$(dirname "$0")"

if [ ! -f ".venv/bin/activate" ]; then
    echo "The virtual environment .venv was not found in $(pwd)."
    echo "Follow the Setup steps in README.md first, then run this script again."
    exit 1
fi

source ".venv/bin/activate"
echo "Starting NIRF Atlas at http://localhost:8501 ..."
echo "The Ask NIRF chat needs internet (Gemini API); every other page works offline."
python -m streamlit run app/Home.py
