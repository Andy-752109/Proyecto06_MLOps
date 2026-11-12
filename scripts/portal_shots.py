"""Capturas de pantalla del portal: levanta uvicorn en un puerto libre y recorre rutas."""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def portal(port: int, env: dict | None = None):
    """Levanta el portal y entrega su URL base; lo detiene al salir."""
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            sys.exit(f"el puerto {port} está ocupado")
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "monitor.portal.app:app", "--port", str(port)],
                           cwd=ROOT, env={**os.environ, **(env or {})},
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        yield base
    finally:
        srv.terminate()


def shoot(pages: list[tuple[str, str, str]], out_dir: Path, port: int = 8768) -> list[dict]:
    """pages: (nombre, ruta, qué muestra). Devuelve [{png, url, status, what}]."""
    out = []
    with portal(port) as base, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        for name, url, what in pages:
            resp = page.goto(base + url)
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(out_dir / f"{name}.png"), full_page=True)
            out.append({"png": f"{name}.png", "url": url, "status": resp.status, "what": what})
        browser.close()
    return out
