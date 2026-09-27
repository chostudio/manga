"""Split full-page manga images into panel crops.

Primary strategy (``detectors.detect_panels``)
-----------------------------------------------
A YOLO model fine-tuned on Manga109 detects the actual drawn panel (frame)
boxes.  This follows the real comic panel borders and is robust to screentone
backgrounds, black gutters, and borderless/bleed panels — the cases that broke
the old white-gutter heuristic.

Fallback strategy (``_split_by_gutters``)
-----------------------------------------
If the model is unavailable or finds fewer than two frames, fall back to the
legacy white-gutter connected-component method, and finally to returning the
whole page unchanged.
"""

import cv2
import numpy as np

from api.detectors import crop_boxes, detect_panels, sort_manga_order

# ---------------------------------------------------------------------------
# Gutter-fallback tuning constants
# ---------------------------------------------------------------------------
_GUTTER_THRESHOLD = 240
_MORPH_KERNEL_RATIO = 0.008
_MIN_AREA_RATIO = 0.01
_MAX_AREA_RATIO = 0.85
_MIN_DIM_PX = 40
_ROW_TOLERANCE_RATIO = 0.06
_PANEL_PADDING = 2


def split_image_into_panels(image_bytes: bytes) -> list[bytes]:
    """Split one manga page into individual panel images (PNG bytes).

    Tries the YOLO panel detector first, then the gutter heuristic, then
    returns the original page unchanged if neither yields multiple panels.
    Panels come back in manga reading order (top-to-bottom rows, right-to-left).
    """
    # ------------------------------------------------------------------
    # 1. Primary: YOLO frame detection
    # ------------------------------------------------------------------
    try:
        boxes = detect_panels(image_bytes)
    except Exception:
        boxes = []
    if len(boxes) >= 2:
        panels = crop_boxes(image_bytes, boxes)
        if len(panels) >= 2:
            return panels

    # ------------------------------------------------------------------
    # 2. Fallback: white-gutter connected components
    # ------------------------------------------------------------------
    gutter_panels = _split_by_gutters(image_bytes)
    if gutter_panels is not None:
        return gutter_panels

    # ------------------------------------------------------------------
    # 3. Final fallback: the whole page
    # ------------------------------------------------------------------
    return [image_bytes]


def _split_by_gutters(image_bytes: bytes) -> list[bytes] | None:
    """Legacy white-gutter splitter. Returns panels, or None if < 2 found."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    img_h, img_w = img.shape[:2]
    total_area = img_h * img_w
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    k_size = max(3, int(min(img_w, img_h) * _MORPH_KERNEL_RATIO))
    if k_size % 2 == 0:
        k_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))

    def _candidates(threshold: int) -> list[tuple[int, int, int, int]]:
        _, gutter_mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
        gutter_mask = cv2.morphologyEx(gutter_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        content_mask = cv2.bitwise_not(gutter_mask)
        contours, _ = cv2.findContours(content_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filled = np.zeros_like(content_mask)
        cv2.drawContours(filled, contours, -1, 255, -1)
        num_labels, _labels, stats, _c = cv2.connectedComponentsWithStats(filled, connectivity=8)

        min_area = total_area * _MIN_AREA_RATIO
        max_area = total_area * _MAX_AREA_RATIO
        out: list[tuple[int, int, int, int]] = []
        for i in range(1, num_labels):
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            w = stats[i, cv2.CC_STAT_WIDTH]
            h = stats[i, cv2.CC_STAT_HEIGHT]
            if not (min_area <= w * h <= max_area):
                continue
            if w < _MIN_DIM_PX or h < _MIN_DIM_PX:
                continue
            out.append((x, y, w, h))
        return out

    candidates = _candidates(_GUTTER_THRESHOLD)
    if len(candidates) < 2:
        candidates = _candidates(200)

    candidates = _merge_overlapping(candidates)
    if len(candidates) < 2:
        return None

    row_tol = int(img_h * _ROW_TOLERANCE_RATIO)
    candidates = sort_manga_order(candidates, row_tol)

    panels: list[bytes] = []
    for (x, y, w, h) in candidates:
        x1 = min(x + _PANEL_PADDING, img_w - 1)
        y1 = min(y + _PANEL_PADDING, img_h - 1)
        x2 = max(x + w - _PANEL_PADDING, x1 + 1)
        y2 = max(y + h - _PANEL_PADDING, y1 + 1)
        crop_img = img[y1:y2, x1:x2]
        if crop_img.size == 0:
            continue
        success, encoded_img = cv2.imencode('.png', crop_img)
        if success:
            panels.append(encoded_img.tobytes())

    return panels if len(panels) >= 2 else None


def _merge_overlapping(
    boxes: list[tuple[int, int, int, int]],
    iou_threshold: float = 0.3,
) -> list[tuple[int, int, int, int]]:
    """Merge bounding boxes that overlap significantly (by IoU)."""
    if not boxes:
        return boxes

    merged = True
    result = list(boxes)

    while merged:
        merged = False
        new_result: list[tuple[int, int, int, int]] = []
        used = set()

        for i in range(len(result)):
            if i in used:
                continue
            x1, y1, w1, h1 = result[i]
            for j in range(i + 1, len(result)):
                if j in used:
                    continue
                x2, y2, w2, h2 = result[j]

                ix = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
                iy = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
                inter = ix * iy
                union = w1 * h1 + w2 * h2 - inter
                iou = inter / union if union > 0 else 0

                if iou > iou_threshold or (inter / (w1 * h1) > 0.8) or (inter / (w2 * h2) > 0.8):
                    nx = min(x1, x2)
                    ny = min(y1, y2)
                    nw = max(x1 + w1, x2 + w2) - nx
                    nh = max(y1 + h1, y2 + h2) - ny
                    x1, y1, w1, h1 = nx, ny, nw, nh
                    used.add(j)
                    merged = True

            new_result.append((x1, y1, w1, h1))
            used.add(i)

        result = new_result

    return result
