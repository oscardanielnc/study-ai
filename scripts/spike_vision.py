"""Compara modelos de vision sobre fotos reales.

Uso:
    python scripts/spike_vision.py ruta/a/carpeta_de_fotos [modelo ...]

Sin modelos usa el configurado en .env. Para comparar con modelos de otros
fabricantes hay que apuntar LLM_BASE_URL a OpenRouter y tener saldo alli.

Escribe una transcripcion por modelo en ./spike-resultados/ y una tabla
comparativa de costo, tiempo y numero de marcas [?].
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.ingest.images import reescalar  # noqa: E402
from app.llm.costs import calcular  # noqa: E402
from app.llm.openrouter import OpenRouterClient  # noqa: E402
from app.llm.prompts import TRANSCRIPCION  # noqa: E402

EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def main(carpeta: str, candidatos: list[str]) -> None:
    ajustes = get_settings()
    fotos = sorted(
        p for p in Path(carpeta).iterdir() if p.suffix.lower() in EXTENSIONES
    )
    if not fotos:
        sys.exit(f"No encontre imagenes en {carpeta}")
    print(f"{len(fotos)} fotos x {len(candidatos)} modelos\n")

    llm = OpenRouterClient(ajustes.openrouter_api_key, base_url=ajustes.llm_base_url)
    salida = Path("spike-resultados")
    salida.mkdir(exist_ok=True)
    resumen: dict[str, dict] = {}

    for modelo in candidatos:
        costo = 0.0
        errores = 0
        t0 = time.time()
        lineas: list[str] = [f"# {modelo}\n"]
        for foto in fotos:
            try:
                r = llm.completar(
                    modelo=modelo,
                    sistema=TRANSCRIPCION,
                    usuario="Transcribe esta imagen.",
                    imagenes=[reescalar(foto.read_bytes())],
                )
                costo += calcular(modelo, r.tokens_in, r.tokens_out)
                texto = r.texto
                print(f"  {modelo:45} {foto.name} ok")
            except Exception as exc:
                errores += 1
                texto = f"*** ERROR: {exc} ***"
                print(f"  {modelo:45} {foto.name} ERROR")
            lineas.append(f"## {foto.name}\n\n{texto}\n")

        archivo = salida / f"{modelo.replace('/', '_')}.md"
        archivo.write_text("\n".join(lineas), encoding="utf-8")
        resumen[modelo] = {
            "costo": round(costo, 4),
            "segundos": round(time.time() - t0, 1),
            "ilegibles": sum(linea.count("[?]") for linea in lineas),
            "errores": errores,
        }

    print(f"\n{'MODELO':45} {'COSTO':>8} {'TIEMPO':>8} {'[?]':>5} {'ERR':>4}")
    for modelo, d in resumen.items():
        print(
            f"{modelo:45} ${d['costo']:>7.4f} {d['segundos']:>7}s "
            f"{d['ilegibles']:>5} {d['errores']:>4}"
        )
    print(f"\nCompara las transcripciones en ./{salida}/")
    print("Criterio, en este orden:")
    print("  1. Errores silenciosos (texto plausible pero falso) -> descalifica")
    print("  2. Uso honesto de [?] en vez de inventar")
    print("  3. Fidelidad del LaTeX y de los bloques [DIAGRAMA: ...]")
    print("  4. Costo (solo desempata: el rango anual es $0,55-$15)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Falta la carpeta de fotos")
    modelos = sys.argv[2:] or [get_settings().modelo_transcripcion]
    main(sys.argv[1], modelos)
