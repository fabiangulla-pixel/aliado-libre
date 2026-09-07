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

El fragmento correcto se lee **del corpus por su identificador**, no de los
resultados de la búsqueda. La diferencia decide el experimento: la primera
versión de este script se quedaba solo con las consultas cuyo fragmento el
buscador ya encontraba, y eso descartaba el 74% con un sesgo brutal — sobrevivía
el 60% del perfil de abogado junior y el 8% del de baja alfabetización. Habría
entrenado al modelo justo con las preguntas que ya acierta, que es lo contrario
de lo que hace falta.

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


def _texto_por_id(indice, fragmento_id: str) -> str:
    """Lee un fragmento del corpus por su identificador, sin pasar por la
    búsqueda. Devuelve cadena vacía si no está o si Chroma falla: un id
    huérfano no puede tumbar la generación entera."""
    try:
        respuesta = indice._coleccion.get(ids=[fragmento_id], include=["documents"])
    except Exception:  # noqa: BLE001 - un id perdido no vale una excepción arriba
        return ""
    documentos = respuesta.get("documents") or []
    return documentos[0] if documentos and documentos[0] else ""


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

    escritos = sin_positivo = sin_texto = 0
    t0 = time.time()
    with salida.open("w", encoding="utf-8") as f:
        for i, caso in enumerate(banco, 1):
            candidatos = indice.buscar(caso["consulta"], k=args.candidatos)

            hallado = next(
                (r for r in candidatos if r.get("id") == caso["fragmento_id"]),
                None,
            )
            if hallado is not None:
                texto_positivo = hallado.get("texto") or ""
            else:
                # El buscador de hoy no lo trae, que es precisamente el caso que
                # más interesa entrenar. Se lee del corpus por id.
                texto_positivo = _texto_por_id(indice, caso["fragmento_id"])
                sin_positivo += 1
            if not texto_positivo:
                sin_texto += 1
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
                        "positivo": texto_positivo[:MAX_CARACTERES],
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
