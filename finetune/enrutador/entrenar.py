"""Enrutador por fuente: de la pregunta a la entidad que probablemente la responde.

"me cortaron la luz" traia conceptos de la Superfinanciera: la busqueda no sabe
que eso es de servicios publicos. Este clasificador lo aprende de las 3.171
consultas que Sonnet etiqueto el 6-oct (finetune/destilar/etiquetas_maestro.json:
la consulta y los fragmentos que eligio como pertinentes). Ninguna de ellas esta
en los bancos de medicion (piloto_100, prueba_200).

Rasgos: el mismo vector e5 de la consulta que ya calcula la busqueda (costo cero
en produccion). Modelo: una regresion logistica por fuente (multietiqueta).
Se guarda como .npz (pesos y nombres), sin pickle.

    .venv/Scripts/python.exe finetune/enrutador/entrenar.py
    -> index/enrutador_fuentes.npz
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding="utf-8")

from index.buscar import MODELO_EMBEDDINGS, PREFIJO_CONSULTA  # noqa: E402

MINIMO_EJEMPLOS = 40  # fuentes con menos ejemplos no se aprenden bien


def main() -> None:
    from sentence_transformers import SentenceTransformer
    from sklearn.linear_model import LogisticRegression

    etiquetas = json.loads((RAIZ / "finetune/destilar/etiquetas_maestro.json").read_text(encoding="utf-8"))
    consultas, fuentes_por_consulta = [], []
    for consulta, dato in etiquetas.items():
        elegidos = dato.get("elegidos") or []
        if not elegidos:
            continue
        # La fuente "principal": la de los dos primeros elegidos (el maestro los ordena).
        consultas.append(consulta)
        fuentes_por_consulta.append({e.split(":", 1)[0] for e in elegidos[:2]})
    conteo = collections.Counter(f for fs in fuentes_por_consulta for f in fs)
    clases = sorted(f for f, n in conteo.items() if n >= MINIMO_EJEMPLOS)
    print(f"{len(consultas)} consultas; fuentes: {dict(conteo.most_common())}")

    modelo = SentenceTransformer(MODELO_EMBEDDINGS, device="cpu")
    X = modelo.encode(
        [PREFIJO_CONSULTA + c for c in consultas],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    rng = np.random.default_rng(20261120)
    orden = rng.permutation(len(consultas))
    corte = int(len(orden) * 0.8)
    entreno, valida = orden[:corte], orden[corte:]

    coef, inter = [], []
    print("\nfuente                 n   AUC-ish: precision@p>=0.5 / cobertura (validacion)")
    for c in clases:
        y = np.array([c in fs for fs in fuentes_por_consulta])
        clf = LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced")
        clf.fit(X[entreno], y[entreno])
        p = clf.predict_proba(X[valida])[:, 1]
        pred = p >= 0.5
        prec = (y[valida] & pred).sum() / max(pred.sum(), 1)
        cob = (y[valida] & pred).sum() / max(y[valida].sum(), 1)
        print(f"{c:22} {conteo[c]:>4}   {prec:.2f} / {cob:.2f}")
        # Reentrenar con todo para el modelo final
        clf.fit(X, y)
        coef.append(clf.coef_[0])
        inter.append(clf.intercept_[0])
    salida = RAIZ / "index" / "enrutador_fuentes.npz"
    np.savez(
        salida,
        coef=np.array(coef, dtype=np.float32),
        intercepto=np.array(inter, dtype=np.float32),
        clases=np.array(clases),
    )
    print(f"\n-> {salida}")


if __name__ == "__main__":
    main()
