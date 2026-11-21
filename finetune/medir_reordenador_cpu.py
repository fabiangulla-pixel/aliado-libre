"""¿Cuánta calidad se pierde sirviendo SIN GPU? (plan del 15-nov-2026)

Para decidir si la web puede vivir en un servidor sin GPU (~30-80 USD/mes) en
vez de en el PC de Fabián. Una sola variable: el reordenador. Los candidatos de
cada consulta se fijan una vez (`pools`) y todas las variantes reordenan
exactamente los mismos.

    python finetune/medir_reordenador_cpu.py pools            # una vez, con el índice
    python finetune/medir_reordenador_cpu.py medir piloto     # todas las variantes, CPU
    python finetune/medir_reordenador_cpu.py medir prueba bge60 <elegida>   # una sola vez

Reglas del proyecto que esto respeta:
- Todo en CPU y con la máquina quieta (sin OCR ni reindexado corriendo): el
  hardware es variable del experimento (D-07), y los tiempos con otra carga
  no valen. Hilos fijados en HILOS, como un servidor pequeño.
- Se elige con piloto_100 (dev); banco_prueba_200 se mira una vez (D-06).
- La salida final pasa por `limitar_sentencias`, igual que en producción.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("HF_HUB_OFFLINE", "0")
HILOS = int(os.environ.get("HILOS", "4"))
BANCOS = {"piloto": "banco_piloto_100.json", "prueba": "banco_prueba_200.json"}
SALIDA = RAIZ / "finetune" / "eval" / "reordenador_cpu"

# nombre -> (modelo, documentos reordenados, max_length, int8)
VARIANTES = {
    "sin": (None, 0, 0, False),
    "bge60": ("BAAI/bge-reranker-v2-m3", 60, 512, False),
    "bge20": ("BAAI/bge-reranker-v2-m3", 20, 512, False),
    "bge10": ("BAAI/bge-reranker-v2-m3", 10, 512, False),
    "bge60q": ("BAAI/bge-reranker-v2-m3", 60, 512, True),
    "bge20q": ("BAAI/bge-reranker-v2-m3", 20, 512, True),
    "mini60": ("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", 60, 512, False),
}


def pools(tam: int = 60, bancos: tuple[str, ...] = ("piloto", "prueba"), maxp: int = 1) -> None:
    """Candidatos fijos por consulta: búsqueda híbrida + `tam` documentos.

    maxp > 1: hasta `maxp` fragmentos por documento (MaxP: el documento vale
    lo que su mejor fragmento; con uno solo, el articulo equivocado de la ley
    correcta la hunde)."""
    os.environ["ALIADO_RERANKER_ACTIVO"] = "0"
    from index.buscar import IndiceBusqueda, un_fragmento_por_documento
    from index.reordenar import CANDIDATOS

    ix = IndiceBusqueda()
    SALIDA.mkdir(parents=True, exist_ok=True)
    for nombre, archivo in BANCOS.items():
        if nombre not in bancos:
            continue
        casos = [
            c
            for c in json.loads((RAIZ / "finetune" / "eval" / archivo).read_text(encoding="utf-8"))
            if c.get("documento_id")
        ]
        filas = []
        for c in casos:
            crudo = ix._buscar_crudo(c["consulta"], k=max(CANDIDATOS, 4 * tam * maxp))
            pool = un_fragmento_por_documento(crudo)[:tam]
            if maxp > 1:
                docs, cuenta = {r["documento_id"] for r in pool}, {}
                pool = []
                for r in crudo:
                    d = r["documento_id"]
                    if d in docs and cuenta.get(d, 0) < maxp:
                        cuenta[d] = cuenta.get(d, 0) + 1
                        pool.append(r)
            filas.append(
                {
                    "consulta": c["consulta"],
                    "esperado": c["documento_id"],
                    "pool": [
                        {
                            "id": r["id"],
                            "documento_id": r.get("documento_id"),
                            "titulo_documento": r.get("titulo_documento"),
                            "texto": r.get("texto"),
                        }
                        for r in pool
                    ],
                }
            )
        sufijo = (str(tam) if tam != 60 else "") + (f"m{maxp}" if maxp > 1 else "")
        (SALIDA / f"pools_{nombre}{sufijo}.json").write_text(
            json.dumps(filas, ensure_ascii=False), encoding="utf-8"
        )
        print(f"{nombre}: {len(filas)} consultas", flush=True)


def _cargar(modelo: str, int8: bool, max_length: int):
    import torch
    from sentence_transformers import CrossEncoder

    torch.set_num_threads(HILOS)
    ce = CrossEncoder(modelo, max_length=max_length, device="cpu")
    if int8:
        # En su sitio: reasignar ce.model rompe cómo CrossEncoder llama al modelo.
        torch.quantization.quantize_dynamic(ce.model, {torch.nn.Linear}, dtype=torch.qint8, inplace=True)
    return ce


def medir(banco: str, nombres: list[str]) -> None:
    from index.buscar import limitar_sentencias
    from index.reordenar import _pasaje

    casos = json.loads((SALIDA / f"pools_{banco}.json").read_text(encoding="utf-8"))
    tope = int(os.environ.get("MAX_CONSULTAS", "0")) or len(casos)
    casos = casos[:tope]
    resultados = {}
    for nombre in nombres or list(VARIANTES):
        modelo, docs, max_len, int8 = VARIANTES[nombre]
        ce = _cargar(modelo, int8, max_len) if modelo else None
        aciertos, tiempos = [], []
        for c in casos:
            pool = c["pool"]
            t = time.perf_counter()
            if ce is not None:
                ventana = pool[:docs]
                puntajes = ce.predict([(c["consulta"], _pasaje(r)) for r in ventana], batch_size=16)
                orden = [r for _, r in sorted(zip(puntajes, ventana, strict=True), key=lambda x: -x[0])]
                pool = orden + pool[docs:]
            tiempos.append(time.perf_counter() - t)
            top = limitar_sentencias(pool, 5)
            aciertos.append(any(r["documento_id"] == c["esperado"] for r in top))
        n = len(casos)
        tiempos.sort()
        resultados[nombre] = {
            "recall_at_5": round(sum(aciertos) / n, 4),
            "aciertos": aciertos,
            "s_consulta_media": round(sum(tiempos) / n, 2),
            "s_consulta_p90": round(tiempos[int(n * 0.9) - 1], 2),
        }
        r = resultados[nombre]
        print(
            f"{nombre:7} recall@5 {r['recall_at_5'] * 100:5.1f}% | {r['s_consulta_media']:6.2f} s/consulta "
            f"(p90 {r['s_consulta_p90']:.2f}) | {HILOS} hilos CPU, n={n}",
            flush=True,
        )
    destino = SALIDA / f"resultados_{banco}_{time.strftime('%Y%m%d_%H%M')}.json"
    destino.write_text(json.dumps({"hilos": HILOS, "variantes": resultados}, indent=1), encoding="utf-8")
    print(f"-> {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    if sys.argv[1] == "pools":
        # pools <tam> [maxp] <bancos...>
        args = sys.argv[2:]
        tam = int(args.pop(0)) if args else 60
        maxp = int(args.pop(0)) if args and args[0].isdigit() else 1
        pools(tam, tuple(args) or ("piloto", "prueba"), maxp)
    else:
        medir(sys.argv[2], sys.argv[3:])
