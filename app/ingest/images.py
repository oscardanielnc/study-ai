import io

from PIL import Image, ImageOps


def reescalar(datos: bytes, lado_max: int = 1100) -> bytes:
    """Reescala a JPEG con el lado mayor <= lado_max. No amplía."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(datos)))
    img = img.convert("RGB")
    if max(img.size) > lado_max:
        img.thumbnail((lado_max, lado_max), Image.Resampling.LANCZOS)
    salida = io.BytesIO()
    img.save(salida, format="JPEG", quality=85, optimize=True)
    return salida.getvalue()
