"""Detector de personas YOLOv8n (Ultralytics) con identidad verificable del artefacto."""
import hashlib
import platform
import time
from pathlib import Path


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class PersonDetector:
    def __init__(self, model_cfg: dict, root: Path):
        import torch
        import ultralytics
        from ultralytics import YOLO

        self.cfg = model_cfg
        path = root / model_cfg["path"]
        self.sha256 = file_sha256(path)  # versión REPORTADA (lo que realmente se cargó)
        self.model = YOLO(str(path))
        self.classes = model_cfg["classes"]
        self.environment = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "ultralytics": ultralytics.__version__,
            "torch": torch.__version__,
            "device": model_cfg["device"],
        }

    @property
    def model_ref(self) -> str:
        return f"{self.cfg['name']}@sha256:{self.sha256[:12]}"

    def predict(self, image):
        """Devuelve (detecciones, inference_ms). Solo se mide la llamada al modelo
        (preprocesamiento + forward + NMS de Ultralytics), sin captura ni escritura."""
        t0 = time.perf_counter()
        res = self.model.predict(
            image,
            conf=self.cfg["conf_floor"],
            iou=self.cfg["nms_iou"],
            imgsz=self.cfg["imgsz"],
            classes=list(self.classes),
            max_det=self.cfg["max_det"],
            device=self.cfg["device"],
            verbose=False,
        )[0]
        ms = (time.perf_counter() - t0) * 1000
        boxes = res.boxes
        dets = []
        for xyxy, conf, cls in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist()):
            cid = int(cls)
            dets.append({
                "class_id": cid,
                "class_name": self.classes.get(cid, str(cid)),
                "score": round(float(conf), 6),
                "bbox_xyxy": [round(v, 1) for v in xyxy],
            })
        dets.sort(key=lambda d: -d["score"])
        return dets, ms
