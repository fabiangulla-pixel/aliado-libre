#!/usr/bin/env python3
"""¿De lo que los colombianos preguntan de verdad, cuánto puede responder el índice?

Todo lo que el proyecto ha medido hasta hoy usa consultas inventadas: el banco
viejo las derivó de los fragmentos que debían recuperar, y el banco piloto las
escribió una IA imitando a ocho perfiles. Las dos cosas son suposiciones sobre
la demanda. `recolectar_consultas_reales.py` trae frases del autocompletar de
Google en Colombia, que son demanda observada.

Con ellas se puede medir algo que ningún banco sintético contesta: **de lo que
la gente realmente pregunta, qué fracción tiene respaldo en el índice**. No
hace falta saber cuál es la respuesta correcta —que exigiría anotar a mano
cientos de consultas—, basta con preguntarle al enrutador, que ya decide eso
con un umbral calibrado y es el mismo que ve el usuario en la GUI.

Es una medición de COBERTURA, no de acierto: dice si hay algo con qué
responder, no si la respuesta sería buena. Pero es la primera cifra del
proyecto que se apoya en demanda real, y es gratis.

Uso:
    ./.venv/Scripts/python.exe finetune/medir_demanda_real.py
    ./.venv/Scripts/python.exe finetune/medir_demanda_real.py --limite 200
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

ENTRADA = RAIZ / "finetune" / "eval" / "consultas_reales_google.json"
SALIDA = RAIZ / "finetune" / "eval" / "cobertura_demanda_real.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()

    if not ENTRADA.exists():
        print(f"Falta {ENTRADA}: corre antes recolectar_consultas_reales.py")
        return 1

    from index.buscar import IndiceBusqueda
    from index.enrutador import decidir

    consultas = json.loads(ENTRADA.read_text(encoding="utf-8"))
    if args.limite:
        consultas = consultas[: args.limite]
    print(f"{len(consultas)} consultas reales del autocompletar de Google (Colombia)")

    print("Cargando índice...")
    t0 = time.time()
    indice = IndiceBusqueda()
    print(f"listo en {time.time() - t0:.0f}s\n")

    filas = []
    por_semilla: dict[str, list[bool]] = defaultdict(list)
    t0 = time.time()
    for i, c in enumerate(consultas, 1):
        resultados = indice.buscar(c["consulta"], k=5)
        decision = decidir(resultados, hay_clave_externa=True)
        filas.append(
            {
                **c,
                "hay_respaldo": decision.responde,
                "motivo": decision.motivo,
                "mejor_puntaje": (resultados[0].get("puntaje") if resultados else 0.0),
                "documentos": [r.get("documento_id") for r in resultados[:3]],
            }
        )
        por_semilla[c["semilla"]].append(decision.responde)
        if i % 50 == 0:
            resta = (time.time() - t0) / i * (len(consultas) - i) / 60
            print(f"  {i}/{len(consultas)}  (~{resta:.0f} min)")

    con = sum(1 for f in filas if f["hay_respaldo"])
    print("\n" + "=" * 74)
    print("COBERTURA SOBRE DEMANDA REAL")
    print("=" * 74)
    print(f"Con respaldo en el índice: {con}/{len(filas)} = {con / len(filas) * 100:.1f}%")
    print(f"Sin respaldo             : {len(filas) - con} consultas\n")

    print("Materias MEJOR cubiertas:")
    orden = sorted(
        ((s, sum(v), len(v)) for s, v in por_semilla.items() if len(v) >= 3),
        key=lambda x: -(x[1] / x[2]),
    )
    for s, a, n in orden[:10]:
        print(f"  {a / n * 100:5.0f}%  {s[:52]:54} ({a}/{n})")
    print("\nMaterias PEOR cubiertas — dónde el corpus le queda debiendo a la gente:")
    for s, a, n in orden[-12:]:
        print(f"  {a / n * 100:5.0f}%  {s[:52]:54} ({a}/{n})")

    SALIDA.write_text(
        json.dumps(
            {"con_respaldo": con, "total": len(filas), "detalle": filas}, ensure_ascii=False, indent=1
        ),
        encoding="utf-8",
    )
    print(f"\nDetalle en {SALIDA}")
    print("\nOjo: esto mide si hay ALGO con qué responder, no si la respuesta")
    print("seria buena. Es cobertura, no acierto.")
    print(f"Semillas cubiertas: {len(por_semilla)} | {dict(Counter(c['nivel'] for c in consultas))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
