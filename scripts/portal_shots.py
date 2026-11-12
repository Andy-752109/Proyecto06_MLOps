"""Capturas de pantalla del portal: levanta uvicorn en un puerto libre y recorre rutas."""
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def shoot(pages: list[tuple[str, str, str]], out_dir: Path, port: int = 8768) -> list[dict]:
    """pages: (nombre, ruta, qué muestra). Devuelve [{png, url, status, what}]."""
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            sys.exit(f"el puerto {port} está ocupado")
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "monitor.portal.app:app", "--port", str(port)],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base, out = f"http://127.0.0.1:{port}", []
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            for name, url, what in pages:
                resp = page.goto(base + url)
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(out_dir / f"{name}.png"), full_page=True)
                out.append({"png": f"{name}.png", "url": url, "status": resp.status, "what": what})
            browser.close()
    finally:
        srv.terminate()
    return out
