import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
WEBAPP_PATH = BASE_DIR / "Webapp.py"

def main():
    if not WEBAPP_PATH.exists():
        print(f"[ERROR] Webapp.py not found: {WEBAPP_PATH}")
        sys.exit(1)

    print(f"[INFO] Starting Streamlit app: {WEBAPP_PATH}")

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(WEBAPP_PATH)
    ]

    subprocess.run(command, cwd=str(BASE_DIR))

if __name__ == "__main__":
    main()