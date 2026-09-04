"""Calibra el umbral a partir del cual la app debe abstenerse de responder.

La precisión no sube inventando mejores respuestas: sube dejando de responder
cuando no hay con qué. Este script recorre los umbrales posibles del puntaje
de fusión y, para cada uno, mide dos cosas que se mueven en direcciones
opuestas:

- **precisión**: de las consultas que SÍ se responden, cuántas tenían el
  documento correcto entre los recuperados.
- **cobertura**: qué proporción de consultas se responde.

Un umbral alto acerca la precisión al 100% respondiendo poco; uno bajo
responde todo con la precisión de hoy. La decisión es de producto, no técnica,
así que el script no elige: imprime la curva y señala los puntos de interés.

Trabaja sobre el JSON que deja finetune/medir_recuperacion.py, así que no
carga el índice ni cuesta nada volver a correrlo con otros criterios.

Uso:
    ./venv/Scripts/python.exe finetune/calibrar_abstencion.py [ruta_resultados.json] [--k 5]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def _curva(filas: list[dict], k: int) -> list[dict]:
    puntajes = sorted({f["puntajes"][0] for f in filas if f.get("puntajes") and f["puntajes"][0]})
    if not puntajes:
        return []
    # como mucho 40 umbrales repartidos por percentiles: más no aporta
    paso = max(1, len(puntajes) // 40)
    curva = []
    for umbral in puntajes[::paso]:
        respondidas = [f for f in filas if f.get("puntajes") and (f["puntajes"][0] or 0) >= umbral]
        if not respondidas:
            continue
        aciertos = sum(1 for f in respondidas if f.get(f"acierto@{k}"))
        curva.append(
            {
                "umbral": umbral,
                "respondidas": len(respondidas),
                "cobertura": len(respondidas) / len(filas),
                "precision": aciertos / len(respondidas),
            }
        )
    return curva


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("resultados", nargs="?", default=str(RAIZ / "eval" / "recuperacion_base.json"))
    p.add_argument("--k", type=int, default=5, help="top-k que se considera acierto")
    args = p.parse_args()

    datos = json.loads(Path(args.resultados).read_text(encoding="utf-8"))
    filas = datos["detalle"]
    if not filas or "puntajes" not in filas[0]:
        raise SystemExit(
            "Este archivo no trae puntajes — se generó antes de que medir_recuperacion.py "
            "los guardara. Hay que volver a correr la medición."
        )

    base = sum(1 for f in filas if f.get(f"acierto@{args.k}")) / len(filas)
    print(f"{len(filas)} consultas | sin abstención: precisión = cobertura·acierto = {base * 100:.1f}%\n")

    curva = _curva(filas, args.k)
    print(f"{'umbral':>8} {'responde':>9} {'cobertura':>10} {'precisión':>10}")
    for punto in curva:
        print(
            f"{punto['umbral']:>8.4f} {punto['respondidas']:>9} "
            f"{punto['cobertura'] * 100:>9.0f}% {punto['precision'] * 100:>9.0f}%"
        )

    print("\nPuntos de interés:")
    for objetivo in (0.80, 0.90, 0.95, 0.99):
        alcanzables = [c for c in curva if c["precision"] >= objetivo]
        if alcanzables:
            mejor = max(alcanzables, key=lambda c: c["cobertura"])
            print(
                f"  precisión ≥{objetivo * 100:.0f}%: umbral {mejor['umbral']:.4f} "
                f"respondiendo el {mejor['cobertura'] * 100:.0f}% de las consultas"
            )
        else:
            print(f"  precisión ≥{objetivo * 100:.0f}%: INALCANZABLE con este recuperador")

    por_perfil = defaultdict(list)
    for f in filas:
        por_perfil[f.get("perfil", "?")].append(f)
    print("\nPrecisión sin abstención, por perfil (para ver a quién se penaliza más):")
    for perfil, fs in sorted(por_perfil.items(), key=lambda x: -len(x[1])):
        acc = sum(1 for f in fs if f.get(f"acierto@{args.k}")) / len(fs)
        print(f"  {perfil:24} {len(fs):>5} consultas   {acc * 100:>5.1f}%")


if __name__ == "__main__":
    main()
