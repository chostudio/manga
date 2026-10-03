"""
Manga-aware detection: panel (frame) boxes on a page, and semantic
sub-elements (face, eyes, hand, person) within a panel.

Panels
------
A YOLO model fine-tuned on Manga109 (``leoxs22/manga-panel-detector-yolo26n``,
classes ``{0: frame, 1: text}``) locates the actual drawn panel boxes, replacing
the old white-gutter heuristic that broke on screentone / black gutters /
borderless art.  Weights are pulled from the Hugging Face hub on first use and
cached under ``~/.cache/huggingface``.

Sub-elements
------------
``dghs-imgutils`` ships anime-domain detectors (``detect_faces``, ``detect_eyes``,
``detect_hands``, ``detect_person``) that fire reliably on manga line art, unlike
the previous YOLOv8-pose model (trained on real humans).  Each returns a list of
``((x0, y0, x1, y1), label, score)`` tuples in pixel coordinates.

All models are loaded lazily and cached as module-level singletons.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
PANEL_REPO = "leoxs22/manga-panel-detector-yolo26n"
PANEL_WEIGHTS = "manga_panel_detector_fp32.pt"
PANEL_CONF = 0.30           # min confidence for a frame box
PANEL_IMGSZ = 1024          # model was exported for full-page inference at 1024
_FRAME_CLASS_ID = 0         # class 0 == "frame" (panel); class 1 == "text"

SUB_ELEMENT_CONF = 0.40     # min confidence for face/eye/hand/person crops
MIN_CROP_PX = 20            # skip crops smaller than this on either edge
_MIN_PANEL_AREA_RATIO = 0.012  # ignore frame boxes smaller than ~1.2% of the page

# Sub-element labels this module can emit (kept in sync with models.SUB_ELEMENT_LABELS)
SUB_ELEMENT_LABELS = ("face", "eyes", "hand", "person")


@dataclass
class DetectedSubElement:
    """One detected sub-region within a panel."""

    label: str          # "face" | "eyes" | "hand" | "person"
    bbox: dict          # {"x": int, "y": int, "w": int, "h": int} — panel-relative pixels
    crop_bytes: bytes   # PNG bytes of the cropped region, ready for tagging/CLIP
    score: float = 0.0  # detector confidence


# ---------------------------------------------------------------------------
# Lazy model singletons
# ---------------------------------------------------------------------------
_panel_model = None  # None = not tried, False = failed, else YOLO instance


def _get_panel_model():
    global _panel_model
    if _panel_model is None:
        try:
            from huggingface_hub import hf_hub_download
            from ultralytics import YOLO

            weights = hf_hub_download(PANEL_REPO, PANEL_WEIGHTS)
            _panel_model = YOLO(weights)
            logger.info("Loaded manga panel detector from %s", weights)
        except Exception as e:  # pragma: no cover - depends on network/weights
            logger.error("Failed to load panel detector: %s", e)
            _panel_model = False
    return _panel_model or None


# ---------------------------------------------------------------------------
# Decoding helpers
# ---------------------------------------------------------------------------

def _decode_bgr(image_bytes: bytes) -> np.ndarray | None:
    """Decode arbitrary image bytes (incl. avif) to an OpenCV BGR array."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is not None:
        return img
    # Fallback via Pillow (handles AVIF/WEBP that cv2 may miss)
    try:
        with Image.open(io.BytesIO(image_bytes)) as pil:
            rgb = pil.convert("RGB")
        return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def _clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))


# ---------------------------------------------------------------------------
# Panel detection
# ---------------------------------------------------------------------------

def detect_panels(page_bytes: bytes) -> list[tuple[int, int, int, int]]:
    """
    Detect panel (frame) boxes on a full manga page.

    Returns a list of ``(x, y, w, h)`` boxes sorted in manga reading order
    (top-to-bottom rows, right-to-left within a row).  Returns ``[]`` if the
    model is unavailable or finds no frames — callers should fall back.
    """
    model = _get_panel_model()
    if model is None:
        return []

    img = _decode_bgr(page_bytes)
    if img is None:
        return []
    img_h, img_w = img.shape[:2]
    total_area = float(img_h * img_w)

    try:
        results = model.predict(img, conf=PANEL_CONF, imgsz=PANEL_IMGSZ, verbose=False)
    except Exception as e:
        logger.warning("Panel detection failed: %s", e)
        return []

    boxes: list[tuple[int, int, int, int]] = []
    for res in results:
        for b in res.boxes:
            if int(b.cls) != _FRAME_CLASS_ID:
                continue
            x0, y0, x1, y1 = (float(v) for v in b.xyxy[0].tolist())
            x = _clamp(int(x0), 0, img_w - 1)
            y = _clamp(int(y0), 0, img_h - 1)
            w = _clamp(int(x1) - x, 1, img_w - x)
            h = _clamp(int(y1) - y, 1, img_h - y)
            if w * h < total_area * _MIN_PANEL_AREA_RATIO:
                continue
            boxes.append((x, y, w, h))

    if not boxes:
        return []

    row_tol = int(img_h * 0.06)
    return sort_manga_order(boxes, row_tol)


def crop_boxes(page_bytes: bytes, boxes: list[tuple[int, int, int, int]]) -> list[bytes]:
    """Crop a page to each ``(x, y, w, h)`` box, returning PNG bytes per box."""
    img = _decode_bgr(page_bytes)
    if img is None:
        return []
    out: list[bytes] = []
    for (x, y, w, h) in boxes:
        crop = img[y : y + h, x : x + w]
        if crop.size == 0:
            continue
        ok, buf = cv2.imencode(".png", crop)
        if ok:
            out.append(buf.tobytes())
    return out


# ---------------------------------------------------------------------------
# Reading-order sort (shared with the gutter fallback in image_split)
# ---------------------------------------------------------------------------

def sort_manga_order(
    boxes: list[tuple[int, int, int, int]],
    row_tolerance: int,
) -> list[tuple[int, int, int, int]]:
    """Group boxes into rows (by y, with tolerance), each row right-to-left."""
    if not boxes:
        return boxes
    sorted_by_y = sorted(boxes, key=lambda b: b[1])
    rows: list[list[tuple[int, int, int, int]]] = []
    current_row = [sorted_by_y[0]]
    current_row_y = sorted_by_y[0][1]
    for box in sorted_by_y[1:]:
        if abs(box[1] - current_row_y) <= row_tolerance:
            current_row.append(box)
        else:
            rows.append(current_row)
            current_row = [box]
            current_row_y = box[1]
    rows.append(current_row)
    result: list[tuple[int, int, int, int]] = []
    for row in rows:
        row.sort(key=lambda b: -b[0])  # right-to-left
        result.extend(row)
    return result


# ---------------------------------------------------------------------------
# Sub-element detection
# ---------------------------------------------------------------------------

def _run_detector(detect_fn, pil_img: Image.Image, label: str) -> list[tuple[dict, str, float]]:
    """Run one imgutils detector, mapping its output to (bbox_dict, label, score)."""
    try:
        raw = detect_fn(pil_img, conf_threshold=SUB_ELEMENT_CONF)
    except TypeError:
        # Some detectors name the arg differently; fall back to positional default.
        raw = detect_fn(pil_img)
    except Exception as e:
        logger.warning("%s detection failed: %s", label, e)
        return []

    out: list[tuple[dict, str, float]] = []
    for (x0, y0, x1, y1), _det_label, score in raw:
        if score < SUB_ELEMENT_CONF:
            continue
        bbox = {"x": int(x0), "y": int(y0), "w": int(x1 - x0), "h": int(y1 - y0)}
        if bbox["w"] < MIN_CROP_PX or bbox["h"] < MIN_CROP_PX:
            continue
        out.append((bbox, label, float(score)))
    return out


def detect_sub_elements(panel_bytes: bytes) -> list[DetectedSubElement]:
    """
    Detect face / eyes / hand / person regions inside a single panel crop.

    Returns an empty list on decode failure or if imgutils is unavailable; a
    failure in any single detector is logged and skipped without aborting.
    """
    img = _decode_bgr(panel_bytes)
    if img is None:
        return []
    img_h, img_w = img.shape[:2]

    try:
        from imgutils.detect.eye import detect_eyes
        from imgutils.detect.face import detect_faces
        from imgutils.detect.hand import detect_hands
        from imgutils.detect.person import detect_person
    except Exception as e:  # pragma: no cover - import guard
        logger.error("imgutils detectors unavailable: %s", e)
        return []

    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    detections: list[tuple[dict, str, float]] = []
    detections += _run_detector(detect_faces, pil_img, "face")
    detections += _run_detector(detect_eyes, pil_img, "eyes")
    detections += _run_detector(detect_hands, pil_img, "hand")
    detections += _run_detector(detect_person, pil_img, "person")

    elements: list[DetectedSubElement] = []
    for bbox, label, score in detections:
        x = _clamp(bbox["x"], 0, img_w - 1)
        y = _clamp(bbox["y"], 0, img_h - 1)
        w = _clamp(bbox["w"], 1, img_w - x)
        h = _clamp(bbox["h"], 1, img_h - y)
        crop = img[y : y + h, x : x + w]
        if crop.size == 0:
            continue
        ok, buf = cv2.imencode(".png", crop)
        if not ok:
            continue
        elements.append(
            DetectedSubElement(
                label=label,
                bbox={"x": x, "y": y, "w": w, "h": h},
                crop_bytes=buf.tobytes(),
                score=score,
            )
        )
    return elements
