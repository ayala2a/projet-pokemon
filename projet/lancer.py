"""API et interface, avec journaux visibles dans docker compose logs python."""
import signal
import subprocess
import sys
import time

processus = []


def arreter(*_):
    for p in processus:
        if p.poll() is None:
            p.terminate()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, arreter)
    signal.signal(signal.SIGINT, arreter)
    processus.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'api:app',
        '--app-dir', '/projet', '--host', '0.0.0.0', '--port', '8000']))
    processus.append(subprocess.Popen([sys.executable, '-m', 'streamlit', 'run',
        '/projet/tableau_de_bord.py', '--server.address=0.0.0.0', '--server.port=8501',
        '--browser.gatherUsageStats=false', '--theme.base=light',
        '--theme.primaryColor=#b63e36', '--theme.backgroundColor=#f6f7fb',
        '--theme.secondaryBackgroundColor=#ffffff', '--theme.textColor=#20283e']))
    try:
        while all(p.poll() is None for p in processus):
            time.sleep(1)
    finally:
        arreter()
        for p in processus:
            p.wait()
