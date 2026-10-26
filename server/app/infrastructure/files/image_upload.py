from __future__ import annotations

import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from app.shared.errors import ApiError


MIME_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
MAX_PIXELS = 8_000_000
MAX_DIMENSION = 4096
OUTPUT_DIMENSION = 1600
MAX_OUTPUT_BYTES = 3_500_000


def clean_upload_image(raw: bytes, mime: str) -> bytes:
    """Decode a claimed photo and produce metadata-free JPEG for the Agent gateway."""
    if mime not in MIME_FORMATS:
        raise ApiError("VALIDATION_ERROR", "请上传 JPEG、PNG 或 WebP 图片")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as probe:
                if probe.format != MIME_FORMATS[mime]:
                    raise ApiError("VALIDATION_ERROR", "图片实际格式与声明格式不一致")
                width, height = probe.size
                if (width < 1 or height < 1 or width > MAX_DIMENSION or
                        height > MAX_DIMENSION or width * height > MAX_PIXELS):
                    raise ApiError("VALIDATION_ERROR", "图片像素尺寸超限，请缩小后重试")
                if getattr(probe, "n_frames", 1) != 1:
                    raise ApiError("VALIDATION_ERROR", "暂不支持动态图片")
                probe.verify()
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source)
                try:
                    oriented.thumbnail((OUTPUT_DIMENSION, OUTPUT_DIMENSION), Image.Resampling.LANCZOS)
                    if oriented.mode in ("RGBA", "LA") or "transparency" in oriented.info:
                        rgba = oriented.convert("RGBA")
                        canvas = Image.new("RGB", rgba.size, "white")
                        canvas.paste(rgba, mask=rgba.getchannel("A"))
                        rgba.close()
                    else:
                        canvas = oriented.convert("RGB")
                    try:
                        for quality in (85, 70, 55, 40):
                            output = io.BytesIO()
                            canvas.save(output, format="JPEG", quality=quality)
                            if output.tell() <= MAX_OUTPUT_BYTES:
                                return output.getvalue()
                    finally:
                        canvas.close()
                finally:
                    oriented.close()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning,
            Image.DecompressionBombError) as error:
        raise ApiError("VALIDATION_ERROR", "图片无法完整解码，请重新选择照片") from error
    raise ApiError("VALIDATION_ERROR", "图片重新编码后仍超过 3.5 MB，请缩小后重试")
