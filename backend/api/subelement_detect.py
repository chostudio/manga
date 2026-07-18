"""
Detect semantically meaningful sub-elements within a manga panel image.

Sub-element classes:
  - face      : tight crop around a character's face (expressions, emotions)
  - hair      : region above the face / top-of-head (long, short, blonde, ...)
  - hand      : crop around each wrist/hand (fist, waving, pointing, ...)
  - clothing  : torso region (dress, skirt, suit, hoodie, ...)

Strategy
--------
1. Run YOLOv8n-pose on the panel.  Each detected person gives 17 COCO keypoints
   from which we *derive* the four crop boxes mathematically — no separate
   per-class models needed.
2. Run YOLOv8n-face as a fallback to catch faces missed by pose (e.g. tiny
   characters, extreme angles, or low-confidence keypoints).
3. De-duplicate overlapping face crops (IoU > 0.6) produced by both passes.

Both YOLO models are loaded lazily and cached as module-level singletons.
Ultralytics auto-downloads model weights to ~/.cache/ultralytics/ on first use.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# COCO keypoint indices (YOLOv8-pose)
# ---------------------------------------------------------------------------
KP_NOSE = 0
KP_LEFT_EYE = 1
KP_RIGHT_EYE = 2
KP_LEFT_EAR = 3
KP_RIGHT_EAR = 4
KP_LEFT_SHOULDER = 5
KP_RIGHT_SHOULDER = 6
KP_LEFT_ELBOW = 7
KP_RIGHT_ELBOW = 8
KP_LEFT_WRIST = 9
KP_RIGHT_WRIST = 10
KP_LEFT_HIP = 11
KP_RIGHT_HIP = 12

# Confidence threshold — keypoints below this are considered unreliable
KP_CONF_THRESH = 0.4

# Minimum crop dimensions (pixels) — smaller crops are skipped
MIN_CROP_PX = 24


@dataclass
class DetectedSubElement:
    """One detected sub-region within a panel."""

    label: str          # "face" | "hair" | "hand" | "clothing"
    bbox: dict          # {"x": int, "y": int, "w": int, "h": int} — panel-relative pixels
    crop_bytes: bytes   # PNG bytes of the cropped region, ready for CLIP


# ---------------------------------------------------------------------------
# Lazy model singletons
# ---------------------------------------------------------------------------
_pose_model = None


def _get_pose_model():
    global _pose_model
    if _pose_model is None:
        try:
            from ultralytics import YOLO
            _pose_model = YOLO("yolov8n-pose.pt")
            logger.info("yolov8n-pose.pt loaded")
        except Exception as e:
            logger.error("Failed to load yolov8n-pose model: %s", e)
            _pose_model = False  # sentinel — don't retry
    return _pose_model or None


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))


def _make_bbox(x: int, y: int, w: int, h: int, img_w: int, img_h: int) -> dict | None:
    """Return a clamped bbox dict, or None if the region is too small."""
    x = _clamp(x, 0, img_w - 1)
    y = _clamp(y, 0, img_h - 1)
    w = _clamp(w, 0, img_w - x)
    h = _clamp(h, 0, img_h - y)
    if w < MIN_CROP_PX or h < MIN_CROP_PX:
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def _crop(img: np.ndarray, bbox: dict) -> bytes:
    """Crop an OpenCV BGR image to bbox and return PNG bytes."""
    x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
    crop = img[y : y + h, x : x + w]
    _, buf = cv2.imencode(".png", crop)
    return buf.tobytes()


def _iou(a: dict, b: dict) -> float:
    """Intersection-over-Union of two bbox dicts."""
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["w"], ay1 + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["w"], by1 + b["h"]
    ix = max(0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
# Keypoint-derived crop derivation
# ---------------------------------------------------------------------------

def _kp(keypoints: np.ndarray, idx: int) -> tuple[float, float, float]:
    """Return (x, y, conf) for keypoint at index idx."""
    return float(keypoints[idx][0]), float(keypoints[idx][1]), float(keypoints[idx][2])


def _kps_centroid(keypoints: np.ndarray, indices: list[int], min_conf: float = KP_CONF_THRESH):
    """Return the mean (x, y) of valid keypoints, or None."""
    pts = [(keypoints[i][0], keypoints[i][1]) for i in indices if keypoints[i][2] >= min_conf]
    if not pts:
        return None
    xs, ys = zip(*pts)
    return float(np.mean(xs)), float(np.mean(ys))


def _derive_crops_from_pose(keypoints: np.ndarray, img_w: int, img_h: int) -> list[tuple[str, dict]]:
    """
    Given one person's keypoints array (shape [17, 3]), derive sub-element bboxes.
    Returns list of (label, bbox_dict).
    """
    results: list[tuple[str, dict]] = []

    # ---- face ----------------------------------------------------------------
    face_pts = [KP_NOSE, KP_LEFT_EYE, KP_RIGHT_EYE, KP_LEFT_EAR, KP_RIGHT_EAR]
    valid_face = [(keypoints[i][0], keypoints[i][1]) for i in face_pts if keypoints[i][2] >= KP_CONF_THRESH]
    if len(valid_face) >= 2:
        xs, ys = zip(*valid_face)
        face_cx = float(np.mean(xs))
        face_cy = float(np.mean(ys))
        face_span = max(float(np.max(xs)) - float(np.min(xs)), 30)
        face_size = int(face_span * 2.2)
        face_bbox = _make_bbox(
            int(face_cx - face_size // 2),
            int(face_cy - face_size // 2),
            face_size, face_size,
            img_w, img_h,
        )
        if face_bbox:
            results.append(("face", face_bbox))

            # ---- hair (region above face bbox) --------------------------------
            hair_y = max(0, face_bbox["y"] - int(face_size * 0.8))
            hair_h = face_bbox["y"] - hair_y + int(face_size * 0.3)
            hair_bbox = _make_bbox(
                face_bbox["x"] - int(face_size * 0.2),
                hair_y,
                face_bbox["w"] + int(face_size * 0.4),
                max(hair_h, MIN_CROP_PX),
                img_w, img_h,
            )
            if hair_bbox:
                results.append(("hair", hair_bbox))

    # ---- hands ---------------------------------------------------------------
    for wrist_idx, label in [(KP_LEFT_WRIST, "hand"), (KP_RIGHT_WRIST, "hand")]:
        wx, wy, wc = _kp(keypoints, wrist_idx)
        if wc < KP_CONF_THRESH:
            continue
        hand_size = int(img_w * 0.12)  # ~12% of panel width per hand
        hand_size = max(hand_size, MIN_CROP_PX * 2)
        hand_bbox = _make_bbox(
            int(wx - hand_size // 2),
            int(wy - hand_size // 2),
            hand_size, hand_size,
            img_w, img_h,
        )
        if hand_bbox:
            results.append(("hand", hand_bbox))

    # ---- clothing (torso: shoulder → hip) ------------------------------------
    shoulder_cx = _kps_centroid(keypoints, [KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER])
    hip_cx = _kps_centroid(keypoints, [KP_LEFT_HIP, KP_RIGHT_HIP])
    ls_x, ls_y, ls_c = _kp(keypoints, KP_LEFT_SHOULDER)
    rs_x, rs_y, rs_c = _kp(keypoints, KP_RIGHT_SHOULDER)
    lh_x, lh_y, lh_c = _kp(keypoints, KP_LEFT_HIP)
    rh_x, rh_y, rh_c = _kp(keypoints, KP_RIGHT_HIP)

    shoulder_pts = [(ls_x, ls_y) for _ in [1] if ls_c >= KP_CONF_THRESH] + \
                   [(rs_x, rs_y) for _ in [1] if rs_c >= KP_CONF_THRESH]
    hip_pts = [(lh_x, lh_y) for _ in [1] if lh_c >= KP_CONF_THRESH] + \
              [(rh_x, rh_y) for _ in [1] if rh_c >= KP_CONF_THRESH]

    if shoulder_pts and hip_pts:
        s_xs, s_ys = zip(*shoulder_pts)
        h_xs, h_ys = zip(*hip_pts)
        torso_x = int(min(min(s_xs), min(h_xs))) - int(img_w * 0.05)
        torso_y = int(min(s_ys))
        torso_w = int(max(max(s_xs), max(h_xs)) - torso_x) + int(img_w * 0.1)
        torso_h = int(max(h_ys)) - torso_y + int(img_h * 0.05)
        clothing_bbox = _make_bbox(torso_x, torso_y, torso_w, torso_h, img_w, img_h)
        if clothing_bbox:
            results.append(("clothing", clothing_bbox))

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_sub_elements(panel_bytes: bytes) -> list[DetectedSubElement]:
    """
    Detect sub-elements in a panel image.

    Uses YOLOv8n-pose to detect persons and derive face, hair, hand, and
    clothing crop regions from body keypoints.  An empty list is returned
    if detection fails or no elements are found.
    """
    try:
        nparr = np.frombuffer(panel_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return []
        img_h, img_w = img.shape[:2]
    except Exception as e:
        logger.warning("Failed to decode panel image: %s", e)
        return []

    elements: list[DetectedSubElement] = []

    # ------------------------------------------------------------------
    # YOLOv8n-pose → derive face/hair/hand/clothing from keypoints
    # ------------------------------------------------------------------
    pose_model = _get_pose_model()
    if pose_model is not None:
        try:
            results = pose_model(img, verbose=False)
            for result in results:
                if result.keypoints is None:
                    continue
                kps_data = result.keypoints.data  # tensor [N, 17, 3]
                for person_kps in kps_data.cpu().numpy():
                    derived = _derive_crops_from_pose(person_kps, img_w, img_h)
                    for label, bbox in derived:
                        crop_bytes = _crop(img, bbox)
                        elements.append(DetectedSubElement(label=label, bbox=bbox, crop_bytes=crop_bytes))
        except Exception as e:
            logger.warning("Pose model inference failed: %s", e)

    return elements
