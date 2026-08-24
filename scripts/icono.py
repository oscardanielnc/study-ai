"""Genera los iconos de la app: un libro abierto sobre el azul tinta.

    .venv/Scripts/python.exe scripts/icono.py

Se dibuja a 1024 y se reduce, que sale mas limpio que dibujar en pequeno.
El contenido cabe dentro del 80% central para que Android pueda recortarlo
con cualquier mascara (circulo, squircle) sin comerse el libro.
"""

from PIL import Image, ImageDraw, ImageFilter

LADO = 1024
CX = LADO // 2

TINTA_ALTA = (37, 64, 94)
TINTA_BAJA = (19, 33, 50)
PAPEL = (252, 250, 246)
PAPEL_LEJOS = (234, 229, 217)
LOMO = (206, 198, 182)
RENGLON = (158, 174, 194)

# Pagina izquierda. Las dos suben hacia fuera desde el lomo, como un libro
# abierto visto de frente. Al reves (lomo alto) el contorno salia un hexagono.
X_CANTO, X_LOMO = 114, CX - 20
ARRIBA_CANTO, ARRIBA_LOMO = 296, 390
ABAJO_CANTO, ABAJO_LOMO = 722, 816
COMBA = 16  # cuanto cae el papel entre el lomo y el canto


def _bezier(p0, p1, p2, n=48):
    return [
        (
            (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1],
        )
        for t in (i / n for i in range(n + 1))
    ]


def _borde(y_canto, y_lomo, comba):
    """Un canto del papel, del lomo hacia fuera, arqueado."""
    medio = ((X_CANTO + X_LOMO) / 2, (y_canto + y_lomo) / 2 + comba)
    return _bezier((X_LOMO, y_lomo), medio, (X_CANTO, y_canto))


def _espejo(puntos):
    return [(LADO - x, y) for x, y in puntos]


# Ambos cantos caen hacia abajo: el papel pesa. Arqueando el de arriba al
# reves salia un hexagono, no un libro.
PAGINA = _borde(ARRIBA_CANTO, ARRIBA_LOMO, COMBA) + _borde(
    ABAJO_CANTO, ABAJO_LOMO, COMBA
)[::-1]


def _y_borde(x, y_canto, y_lomo, comba):
    """Altura del canto arqueado en una x. Los renglones lo siguen en vez de
    quedarse horizontales, que era lo que delataba el dibujo."""
    t = (X_LOMO - x) / (X_LOMO - X_CANTO)
    recta = y_lomo + (y_canto - y_lomo) * t
    return recta + comba * 2 * t * (1 - t)


def _renglones(d, izquierda):
    """Tres por pagina. Con mas, a 48 px se vuelven una mancha gris."""
    x0, x1 = X_CANTO + 74, X_LOMO - 44
    for i in range(3):
        f = 0.32 + i * 0.20
        p = []
        for k in range(13):
            x = x0 + (x1 - x0) * k / 12
            arriba = _y_borde(x, ARRIBA_CANTO, ARRIBA_LOMO, COMBA)
            abajo = _y_borde(x, ABAJO_CANTO, ABAJO_LOMO, COMBA)
            p.append((x, arriba + (abajo - arriba) * f))
        d.line(p if izquierda else _espejo(p), fill=RENGLON, width=27, joint="curve")


def dibujar() -> Image.Image:
    # Degradado vertical: un plano liso se ve muerto al lado de otros iconos.
    img = Image.new("RGB", (LADO, LADO))
    d = ImageDraw.Draw(img)
    for y in range(LADO):
        t = y / (LADO - 1)
        d.line(
            [(0, y), (LADO, y)],
            fill=tuple(round(a + (b - a) * t) for a, b in zip(TINTA_ALTA, TINTA_BAJA)),
        )

    # Sombra difusa aparte: pintada encima del fondo se veia como un borde
    # sucio en vez de despegar el libro.
    sombra = Image.new("L", (LADO, LADO), 0)
    ImageDraw.Draw(sombra).polygon(
        [(x, y + 24) for x, y in PAGINA + _espejo(PAGINA)[::-1]], fill=140
    )
    img.paste(
        Image.new("RGB", (LADO, LADO), (10, 19, 30)),
        (0, 0),
        sombra.filter(ImageFilter.GaussianBlur(28)),
    )

    d = ImageDraw.Draw(img)
    d.polygon(PAGINA, fill=PAPEL_LEJOS)
    d.polygon(_espejo(PAGINA), fill=PAPEL)
    # El lomo es la union de las dos paginas, no una linea pintada encima.
    d.polygon(
        [
            (X_LOMO, ARRIBA_LOMO),
            (LADO - X_LOMO, ARRIBA_LOMO),
            (LADO - X_LOMO, ABAJO_LOMO),
            (X_LOMO, ABAJO_LOMO),
        ],
        fill=LOMO,
    )

    _renglones(d, True)
    _renglones(d, False)
    return img


# Cloudflare cachea /icons/ sin caducidad y el token no tiene permiso de
# purga: la unica forma de que un icono nuevo llegue de verdad es publicarlo
# con otro nombre. Al cambiar el dibujo, sube este numero y actualiza
# manifest.json, index.html y android/twa-manifest.json.
VERSION = 2


if __name__ == "__main__":
    grande = dibujar()
    for lado in (512, 192):
        grande.resize((lado, lado), Image.Resampling.LANCZOS).save(
            f"static/icons/icon-{lado}-v{VERSION}.png"
        )
        print(f"static/icons/icon-{lado}-v{VERSION}.png")
