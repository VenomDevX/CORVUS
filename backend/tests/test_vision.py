import pytest

from corvus.automation import vision
from corvus.automation.vision import TextBox


def fake_boxes(*items) -> list[TextBox]:
    # items: (text, x, y, conf)
    return [TextBox(text=t, x=x, y=y, confidence=c) for t, x, y, c in items]


def test_locate_text_exact_match_wins(monkeypatch):
    monkeypatch.setattr(vision, "read_text_boxes", lambda p: fake_boxes(
        ("Save As", 10, 10, 0.9), ("Save", 20, 40, 0.95), ("Cancel", 30, 40, 0.9),
    ))
    box = vision.locate_text("img.png", "Save")
    assert box.text == "Save" and box.x == 20


def test_locate_text_substring_when_no_exact(monkeypatch):
    monkeypatch.setattr(vision, "read_text_boxes", lambda p: fake_boxes(
        ("Sign in with Google", 5, 5, 0.9), ("Sign up", 5, 30, 0.9),
    ))
    box = vision.locate_text("img.png", "sign in")
    assert "Sign in" in box.text


def test_locate_text_token_overlap_fallback(monkeypatch):
    monkeypatch.setattr(vision, "read_text_boxes", lambda p: fake_boxes(
        ("Open Downloads Folder", 5, 5, 0.9), ("Close", 5, 30, 0.9),
    ))
    box = vision.locate_text("img.png", "downloads")
    assert "Downloads" in box.text


def test_locate_text_no_match_returns_none(monkeypatch):
    monkeypatch.setattr(vision, "read_text_boxes", lambda p: fake_boxes(
        ("Apple", 5, 5, 0.9), ("Banana", 5, 30, 0.9),
    ))
    assert vision.locate_text("img.png", "zzz qqq") is None


def test_extract_text_reading_order(monkeypatch):
    monkeypatch.setattr(vision, "read_text_boxes", lambda p: fake_boxes(
        ("second", 10, 50, 0.9), ("first", 10, 10, 0.9), ("third", 10, 90, 0.9),
    ))
    assert vision.extract_text("img.png") == "first\nsecond\nthird"


class FakeProvider:
    def __init__(self, models):
        self._models = models

    async def list_models(self):
        return self._models

    async def describe_image(self, path, model):
        return f"a description via {model}"


async def test_find_vision_model_detects_llava():
    assert await vision.find_vision_model(FakeProvider(["qwen2.5-coder", "llava:13b"])) == "llava:13b"
    assert await vision.find_vision_model(FakeProvider(["qwen2.5-coder"])) is None


async def test_describe_image_degrades_to_ocr_without_vision_model(monkeypatch):
    monkeypatch.setattr(vision, "extract_text", lambda p: "OK button\nCancel")
    result = await vision.describe_image(FakeProvider(["qwen2.5-coder"]), "x.png")
    assert result["has_text"] is True
    assert "description" not in result


async def test_describe_image_uses_vision_model_when_present(monkeypatch):
    monkeypatch.setattr(vision, "extract_text", lambda p: "")
    result = await vision.describe_image(FakeProvider(["llava:13b"]), "x.png")
    assert result["description"] == "a description via llava:13b"
    assert result["vision_model"] == "llava:13b"


def test_real_ocr_round_trip(tmp_path):
    # Prove the OCR engine reads text off a generated image, end to end.
    Image = pytest.importorskip("PIL.Image")
    from PIL import ImageDraw

    img = Image.new("RGB", (320, 120), "white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 40), "Corvus", fill="black")
    path = tmp_path / "text.png"
    img.save(path)

    text = vision.extract_text(str(path)).lower()
    assert "corvus" in text
