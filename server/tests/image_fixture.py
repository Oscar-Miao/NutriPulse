"""Deterministic synthetic photos; no user images enter automated tests."""

import base64
import hashlib
import io

from PIL import Image


def image_bytes(label: str, image_format: str = "JPEG") -> bytes:
    seed = hashlib.sha256(label.encode("utf-8")).digest()
    pixels = [((x * 31 + y * 17 + seed[(x + y) % 32]) % 256,
               (x * 13 + y * 37 + seed[(x * 3 + y) % 32]) % 256,
               (x * 29 + y * 11 + seed[(x + y * 5) % 32]) % 256)
              for y in range(96) for x in range(96)]
    with Image.new("RGB", (96, 96)) as picture:
        picture.putdata(pixels)
        output = io.BytesIO()
        picture.save(output, format=image_format, quality=90)
        return output.getvalue()


def encoded_jpeg(label: str) -> str:
    return base64.b64encode(image_bytes(label)).decode("ascii")
