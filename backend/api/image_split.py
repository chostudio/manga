"""Split full-page manga images into panel crops."""

import cv2
import numpy as np

def split_image_into_panels(image_bytes: bytes) -> list[bytes]:
    """Split one page into panel images using OpenCV."""
    # Decode image bytes to numpy array
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return [image_bytes]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Thresholding to find black panel borders
    # Invert the image so that the black borders become white
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    
    # Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    panels = []
    min_area = (img.shape[0] * img.shape[1]) * 0.02 # Min 2% of image area
    
    bounding_boxes = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > min_area:
            x, y, w, h = cv2.boundingRect(cnt)
            # Basic check to ensure it's somewhat panel-shaped, avoid very long thin lines
            if w > 50 and h > 50:
                bounding_boxes.append((x, y, w, h))
    
    # If no panels found, return original image
    if not bounding_boxes:
        return [image_bytes]
    
    # Sort bounding boxes top-to-bottom, right-to-left
    # First sort by Y (top to bottom) with some tolerance
    bounding_boxes.sort(key=lambda b: (b[1] // 100, -b[0]))
    
    for (x, y, w, h) in bounding_boxes:
        crop_img = img[y:y+h, x:x+w]
        success, encoded_img = cv2.imencode('.png', crop_img)
        if success:
            panels.append(encoded_img.tobytes())
            
    if not panels:
        return [image_bytes]
        
    return panels
