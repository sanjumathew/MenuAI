from typing import List
import os
import pytesseract
from PIL import Image, ImageOps
import cv2
import numpy as np
from dotenv import load_dotenv

# Load .env if present so TESSERACT_CMD can be set in development
load_dotenv()
# Allow overriding tesseract binary via env var `TESSERACT_CMD`
tess_cmd = os.getenv("TESSERACT_CMD")
if tess_cmd:
    pytesseract.pytesseract.tesseract_cmd = tess_cmd

# Simple preprocessing + tesseract OCR for prototype

def preprocess_image(path: str) -> np.ndarray:
    # Try reading with OpenCV first (fast), but fall back to PIL for formats
    # OpenCV builds may not support newer codecs like AVIF — use PIL as fallback.
    img = cv2.imread(path)
    if img is None:
        try:
            pil = Image.open(path).convert('RGB')
            img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        except Exception as e:
            raise FileNotFoundError(f"Unable to read image {path}: {e}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # resize for better OCR
    h, w = gray.shape
    scale = 1600 / max(h, w)
    if scale > 1:
        gray = cv2.resize(gray, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_LINEAR)
    # bilateral filter and adaptive threshold
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2)
    return th


def ocr_from_image(path: str) -> List[str]:
    img = preprocess_image(path)
    pil = Image.fromarray(img)
    try:
        text = pytesseract.image_to_string(pil)
    except pytesseract.pytesseract.TesseractNotFoundError:
        # Raise a clear error for the calling code to handle/log
        raise FileNotFoundError(
            "Tesseract not found. Install Tesseract and ensure it's on your PATH, "
            "or set TESSERACT_CMD in a .env file to the tesseract executable path."
        )
    # basic split into lines
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines
