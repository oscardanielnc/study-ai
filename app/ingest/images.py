import io

from PIL import Image, ImageOps

# Un PNG de pocos KB puede declarar 60.000 x 60.000 px y ocupar 10 GB al
# abrirlo. Pillow avisa por encima de 178 Mpx pero sigue adelante; aqui se
# corta. 40 Mpx es mas del doble de lo que da un movil de gama alta.
MAX_PIXELES = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELES


class BombaDeImagen(Exception):
    """La imagen declara mas pixeles de los que tiene sentido procesar."""


def reescalar(datos: bytes, lado_max: int = 1100) -> bytes:
    """Reescala a JPEG con el lado mayor <= lado_max. No amplia."""
    try:
        img = Image.open(io.BytesIO(datos))
        ancho, alto = img.size
        if ancho * alto > MAX_PIXELES:
            raise BombaDeImagen(
                f"La imagen declara {ancho}x{alto} px, demasiado para procesarla."
            )
        img = ImageOps.exif_transpose(img)
    except Image.DecompressionBombError as exc:
        raise BombaDeImagen(str(exc)) from exc
    img = img.convert("RGB")
    if max(img.size) > lado_max:
        img.thumbnail((lado_max, lado_max), Image.Resampling.LANCZOS)
    salida = io.BytesIO()
    img.save(salida, format="JPEG", quality=85, optimize=True)
    return salida.getvalue()
