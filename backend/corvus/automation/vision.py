"""Computer vision for Corvus.

Offline, model-optional. OCR (rapidocr-onnxruntime) reads text and its bounding
boxes from screenshots and uploaded images, which powers two things the product
spec asks for:

  * understanding screenshots / uploaded images (extract their text), and
  * locating an on-screen UI element by its label and returning click
    coordinates, so a native (non-web) window can be driven by sight.

If a vision-capable Ollama model is later pulled (llava / llama3.2-vision), the
`describe_image` path uses it for a full visual description; otherwise it
degrades to the OCR text, which is the reliable offline signal. No cloud, no
API keys, no system binaries.
"""

import threading
from dataclasses import dataclass
from pathlib import Path

import structlog

log = structlog.get_logger("corvus")

_ocr = None
_ocr_lock = threading.Lock()

VISION_MODEL_HINTS = ("llava", "vision", "bakllava", "moondream", "minicpm-v")


def _engine():
    global _ocr
    with _ocr_lock:
        if _ocr is None:
            from rapidocr_onnxruntime import RapidOCR

            log.info("ocr_engine_loading")
            _ocr = RapidOCR()
            log.info("ocr_engine_ready")
    return _ocr


@dataclass
class TextBox:
    text: str
    # Center of the detected text, in image pixels.
    x: int
    y: int
    confidence: float


def read_text_boxes(image_path: str) -> list[TextBox]:
    """OCR an image into text fragments with their center coordinates."""
    result, _ = _engine()(image_path)
    boxes: list[TextBox] = []
    for entry in result or []:
        quad, text, score = entry
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        boxes.append(
            TextBox(
                text=text.strip(),
                x=int(sum(xs) / len(xs)),
                y=int(sum(ys) / len(ys)),
                confidence=float(score),
            )
        )
    return boxes


def extract_text(image_path: str) -> str:
    """All readable text in an image, top-to-bottom reading order."""
    boxes = sorted(read_text_boxes(image_path), key=lambda b: (b.y, b.x))
    return "\n".join(b.text for b in boxes if b.text)


def locate_text(image_path: str, query: str) -> TextBox | None:
    """Find the on-screen text best matching `query`, for coordinate clicking.

    Prefers an exact case-insensitive label, then a substring, then the closest
    token overlap - good enough to hit a button labelled "Save" or "Sign in".
    """
    query_l = query.lower().strip()
    boxes = [b for b in read_text_boxes(image_path) if b.text]
    if not boxes:
        return None

    exact = [b for b in boxes if b.text.lower() == query_l]
    if exact:
        return max(exact, key=lambda b: b.confidence)

    contains = [b for b in boxes if query_l in b.text.lower()]
    if contains:
        return min(contains, key=lambda b: len(b.text))

    q_tokens = set(query_l.split())
    scored = [
        (len(q_tokens & set(b.text.lower().split())), b.confidence, b)
        for b in boxes
    ]
    best = max(scored, key=lambda s: (s[0], s[1]))
    return best[2] if best[0] > 0 else None


async def find_vision_model(provider) -> str | None:
    """Return an installed Ollama vision model name, if any."""
    try:
        models = await provider.list_models()
    except Exception:
        return None
    for name in models:
        if any(hint in name.lower() for hint in VISION_MODEL_HINTS):
            return name
    return None


async def describe_image(provider, image_path: str) -> dict:
    """Understand an image: OCR text always, plus a visual description when a
    vision model is available."""
    text = extract_text(image_path)
    result = {"text": text, "has_text": bool(text)}

    model = await find_vision_model(provider)
    if model and hasattr(provider, "describe_image"):
        try:
            result["description"] = await provider.describe_image(image_path, model)
            result["vision_model"] = model
        except Exception as exc:
            log.warning("vision_describe_failed", error=str(exc))
    return result
