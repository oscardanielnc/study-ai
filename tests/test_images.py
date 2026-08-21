import io

from PIL import Image

from app.ingest.images import reescalar


def _png(ancho: int, alto: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_reduce_el_lado_mayor_al_limite():
    salida = reescalar(_png(4000, 3000), lado_max=1100)
    assert Image.open(io.BytesIO(salida)).size == (1100, 825)


def test_no_amplia_imagenes_pequenas():
    salida = reescalar(_png(400, 300), lado_max=1100)
    assert Image.open(io.BytesIO(salida)).size == (400, 300)


def test_devuelve_jpeg():
    assert Image.open(io.BytesIO(reescalar(_png(2000, 2000)))).format == "JPEG"


def test_reduce_el_peso_del_fichero():
    original = _png(4000, 3000)
    assert len(reescalar(original)) < len(original)
