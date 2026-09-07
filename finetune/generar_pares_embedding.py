"""Arma el material para afinar el embedding sobre ESTE corpus y ESTAS preguntas.

Por qué esto y no otra cosa: lo medido dice que el cuello de botella es la
recuperación, y que el fallo se concentra en cómo está escrita la pregunta —el
perfil de abogado encuentra su documento varias veces más a menudo que quien
pregunta con sus palabras. Un embedding genérico no cierra esa distancia porque
nunca vio a nadie llamar "me echaron del trabajo estando enfermo" a una
sentencia sobre estabilidad laboral reforzada. Afinarlo con pares reales
(consulta coloquial -> fragmento que de verdad la responde) es la única forma
barata de enseñarle ese salto.

El material sale del banco coloquial, que ya trae la verdad de referencia:
cada consulta tiene el fragmento del que fue generada.

**Solo se usa la partición dev.** La de prueba queda intacta para medir después;
entrenar con ella sería medirse a sí mismo (ver
[[feedback_medir_mejora_sobre_datos_no_vistos]]).

Negativos difíciles: para cada consulta se le pide al buscador actual sus
mejores candidatos y se toman los que NO son el fragmento correcto. Son los
errores que el buscador comete hoy — exactamente lo que hay que enseñarle a
distinguir. Un negativo al azar del corpus no enseña nada: ya sabe que un
decreto de aduanas no responde una pregunta sobre pensiones.

Uso:
    ./venv/Scripts/python.exe finetune/generar_pares_embedding.py [--negativos 4]

Salida: finetune/data/pares_embedding.jsonl con
    {"consulta": str, "positivo": str, "negativos": [str, ...]}
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ.parent))

# Un fragmento larguísimo no aporta más señal y sí multiplica el costo de
# entrenar: el modelo trunca a 512 tokens de todas formas.
MAX_CARACTERES = 2000


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--negativos", type=int, default=4, help="negativos difíciles por consulta")
    p.add_argument("--candidatos", type=int, default=12, help="cuántos candidatos pedir al buscador")
    p.add_argument("--banco", default=str(RAIZ / "eval" / "banco_coloquial_dev.json"))
    p.add_argument("--salida", default=str(RAIZ / "data" / "pares_embedding.jsonl"))
    args = p.parse_args()

    banco = json.loads(Path(args.banco).read_text(encoding="utf-8"))
    print(f"{len(banco)} consultas en {Path(args.banco).name}")

    from index.buscar import IndiceBusqueda

    print("Cargando índice...")
    t0 = time.time()
    indice = IndiceBusqueda()
    print(f"listo en {time.time() - t0:.0f}s")

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)

    escritos = sin_positivo = 0
    t0 = time.time()
    with salida.open("w", encoding="utf-8") as f:
        for i, caso in enumerate(banco, 1):
            candidatos = indice.buscar(caso["consulta"], k=args.candidatos)

            positivo = next(
                (r for r in candidatos if r.get("id") == caso["fragmento_id"]),
                None,
            )
            if positivo is None:
                # El buscador de hoy no trae el fragmento correcto ni entre 12.
                # No se puede fabricar el positivo desde aquí sin leerlo del
                # corpus por id; se cuenta y se sigue. Ese número es, en sí,
                # una medición: dice cuánto material se pierde por el mismo
                # problema que se quiere arreglar.
                sin_positivo += 1
                continue

            negativos = [
                (r.get("texto") or "")[:MAX_CARACTERES]
                for r in candidatos
                if r.get("id") != caso["fragmento_id"] and r.get("documento_id") != caso.get("documento_id")
            ][: args.negativos]
            if not negativos:
                continue

            f.write(
                json.dumps(
                    {
                        "consulta": caso["consulta"],
                        "perfil": caso["perfil"],
                        "positivo": (positivo.get("texto") or "")[:MAX_CARACTERES],
                        "negativos": negativos,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            escritos += 1

            if i % 50 == 0:
                transcurrido = time.time() - t0
                restante = transcurrido / i * (len(banco) - i)
                print(
                    f"  {i}/{len(banco)} — {escritos} pares, "
                    f"{transcurrido / 60:.0f} min, ~{restante / 60:.0f} min restantes"
                )

    print(f"\n{escritos} pares en {salida}")
    print(
        f"{sin_positivo} consultas descartadas ({sin_positivo / len(banco) * 100:.0f}%): "
        f"el buscador actual no trae su propio fragmento ni entre {args.candidatos}."
    )


if __name__ == "__main__":
    main()
