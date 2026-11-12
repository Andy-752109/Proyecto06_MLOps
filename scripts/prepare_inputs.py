"""Prepara las entradas visuales del proyecto.

1. Descarga data/videos/vtest.avi (muestra de peatones de OpenCV) si no existe.
2. Descarga modelo/yolov8n.pt (Ultralytics assets v8.3.0) si no existe.
3. Genera data/videos/vtest_blur7.avi: el mismo video con desenfoque gaussiano
   sigma=7 (simula una lente desenfocada) para el escenario C2.
4. Verifica/escribe data/videos/SHA256SUMS.

El desenfoque modifica la ENTRADA; las puntuaciones de C2 salen de inferencia real.
"""
import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "data/videos/vtest.avi"
BLUR = ROOT / "data/videos/vtest_blur7.avi"
MODEL = ROOT / "modelo/yolov8n.pt"
SUMS = ROOT / "data/videos/SHA256SUMS"

URLS = {
    VIDEO: "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/vtest.avi",
    MODEL: "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
}
EXPECTED = {
    VIDEO: "45cddc9490be69345cbdab64ca583be65987e864ca408038e648db99e10516cf",
    MODEL: "f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36",
}
BLUR_SIGMA = 7.0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_download(path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"descargando {URLS[path]} -> {path.relative_to(ROOT)}")
        urllib.request.urlretrieve(URLS[path], path)
    got = sha256(path)
    if got != EXPECTED[path]:
        sys.exit(f"SHA-256 inesperado para {path}: {got}")
    print(f"ok {path.relative_to(ROOT)} {got}")


def make_blur(force: bool) -> None:
    if BLUR.exists() and not force:
        print(f"ya existe {BLUR.relative_to(ROOT)} (usa --force para regenerar)")
        return
    cap = cv2.VideoCapture(str(VIDEO))
    fps = cap.get(cv2.CAP_PROP_FPS)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out = cv2.VideoWriter(str(BLUR), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
    n = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        out.write(cv2.GaussianBlur(frame, (0, 0), BLUR_SIGMA))
        n += 1
    out.release()
    cap.release()
    print(f"generado {BLUR.relative_to(ROOT)}: {n} frames, {fps} fps, sigma={BLUR_SIGMA}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="regenera el video desenfocado")
    args = ap.parse_args()
    ensure_download(VIDEO)
    ensure_download(MODEL)
    make_blur(args.force)
    lines = [f"{sha256(p)}  {p.name}" for p in (VIDEO, BLUR)]
    if SUMS.exists() and not args.force:
        recorded = SUMS.read_text().split()
        if sha256(BLUR) not in recorded:
            print("AVISO: vtest_blur7.avi difiere del SHA256SUMS versionado "
                  "(otra versión de OpenCV puede codificar distinto); usa el archivo versionado.")
    else:
        SUMS.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
