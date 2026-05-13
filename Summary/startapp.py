import subprocess
import sys

subprocess.run([
    sys.executable,
    "-m",
    "streamlit",
    "run",
    "app.py",
    "--server.address=0.0.0.0",
    "--server.port=8501"
])

# cd /workspaces/Personal_CodeSpace/Summary
# source .venv/bin/activate
# pip install streamlit
# python startapp.py