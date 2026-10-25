"""Photo preprocessing: one resized JPEG is used for both the Sarvam call and the email attachment."""
import io

from PIL import Image, ImageOps

MAX_SIDE = 1024
JPEG_QUALITY = 85


def resize_photo(image_bytes: bytes) -> bytes:
    """Upright JPEG, max 1024 px on the longest side, quality 85.

    The output has no EXIF, so read GPS with location.gps_from_photo() first.
    """
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes)))
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    if img.mode != "RGB":
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()
