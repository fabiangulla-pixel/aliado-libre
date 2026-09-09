"""Genera una hoja para que una persona compruebe si el juez automático acierta.

Un juez de IA no es verdad de referencia. Dijo que en la mayoría de los "fallos"
había un documento que sí respondía, y de ese número depende si el recall del
proyecto es el que se reporta o casi el triple. Antes de reescribir los objetivos
con esa cifra, alguien tiene que mirar unos cuantos casos. El porcentaje concreto
se lee de la auditoría y se imprime en la hoja: no se escribe aquí, porque cada
vez que se vuelve a auditar cambia.

Se eligen casos repartidos entre los dos veredictos —no solo los "sí", que es
donde el juez podría estar siendo blando— y se muestran la pregunta y los cinco
documentos tal como los vio él. El veredicto del juez va oculto detrás de un
botón: verlo antes contamina el juicio propio.

Uso:
    .venv/Scripts/python.exe finetune/hoja_revision_humana.py [--casos 20]
"""

from __future__ import annotations

import argparse
import html
import json
import random
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--casos", type=int, default=20)
    p.add_argument("--auditoria", default=str(RAIZ / "eval" / "auditoria_metrica.json"))
    p.add_argument("--candidatos", default=str(RAIZ / "eval" / "candidatos_prueba.json"))
    p.add_argument("--salida", default=str(RAIZ / "eval" / "revision_humana.html"))
    args = p.parse_args()

    crudo = json.loads(Path(args.auditoria).read_text(encoding="utf-8"))
    auditoria = crudo["detalle"]
    # El porcentaje se calcula del archivo, no se escribe a mano: esta hoja se
    # regenera cada vez que se vuelve a auditar, y una cifra cableada convierte
    # el instrumento de comprobacion en algo que hay que comprobar.
    n_auditados = crudo.get("n") or len(auditoria)
    pct_juez = round(sum(1 for x in auditoria if x["responde"]) / n_auditados * 100)
    candidatos = {c["consulta"]: c for c in json.loads(Path(args.candidatos).read_text(encoding="utf-8"))}

    dijo_si = [x for x in auditoria if x["responde"]]
    dijo_no = [x for x in auditoria if not x["responde"]]
    random.seed(7)  # misma muestra si se vuelve a generar
    # Proporción parecida a la real, pero con suficientes "no" para poder
    # detectar también el error contrario (que el juez sea demasiado duro).
    n_no = max(4, args.casos // 4)
    muestra = random.sample(dijo_si, min(args.casos - n_no, len(dijo_si))) + random.sample(
        dijo_no, min(n_no, len(dijo_no))
    )
    random.shuffle(muestra)

    filas = []
    for i, caso in enumerate(muestra, 1):
        fuente = candidatos.get(caso["consulta"])
        if not fuente:
            continue
        docs = "".join(
            f"<details><summary>Documento {j}</summary><pre>{html.escape(c['texto'][:1500])}</pre></details>"
            for j, c in enumerate(fuente["candidatos"][:5], 1)
        )
        veredicto = "SÍ responde" if caso["responde"] else "NO responde"
        filas.append(f"""
<article>
  <h2>{i}. {html.escape(caso["consulta"])}</h2>
  <p class="perfil">perfil: {html.escape(caso["perfil"])}</p>
  {docs}
  <p class="pregunta">¿Alguno de esos cinco responde la pregunta?</p>
  <div class="botones">
    <button onclick="marcar({i}, 'si')">Sí responde</button>
    <button onclick="marcar({i}, 'no')">No responde</button>
    <span id="m{i}" class="marca"></span>
  </div>
  <details class="juez"><summary>Ver qué dijo el juez automático</summary>
    <p><strong>{veredicto}</strong> — {html.escape(caso["razon"])}</p>
    <input type="hidden" id="j{i}" value="{"si" if caso["responde"] else "no"}">
  </details>
</article>""")

    documento = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>Revisión humana del juez automático</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 46rem; margin: 2rem auto; padding: 0 1rem;
         line-height: 1.55; color: #1d1a17; background: #faf8f5; }}
  h1 {{ font-size: 1.5rem; }}
  article {{ border-top: 1px solid #d9d2c8; padding: 1.4rem 0; }}
  h2 {{ font-size: 1.1rem; font-weight: normal; }}
  .perfil {{ color: #7a6f63; font-size: .85rem; margin-top: -.6rem; }}
  pre {{ white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: .8rem;
         background: #fff; border: 1px solid #e5ded4; padding: .7rem; }}
  summary {{ cursor: pointer; color: #7b2d26; }}
  .pregunta {{ font-weight: bold; }}
  button {{ font: inherit; padding: .4rem .9rem; margin-right: .5rem; cursor: pointer;
            border: 1px solid #7b2d26; background: #fff; color: #7b2d26; border-radius: 3px; }}
  .marca {{ font-weight: bold; }}
  .juez {{ margin-top: .8rem; font-size: .9rem; }}
  #resumen {{ position: sticky; bottom: 0; background: #7b2d26; color: #fff;
              padding: .8rem 1rem; border-radius: 4px 4px 0 0; }}
</style></head><body>
<h1>¿Acierta el juez automático?</h1>
<p>El juez dijo que en el <strong>{pct_juez}%</strong> de los {n_auditados} casos que
contábamos como fallo había un documento que sí respondía. De esa cifra depende que
el recall del proyecto sea el que se reporta o casi el triple, así que conviene
comprobarla a mano.</p>
<p>Para cada caso: lee la pregunta, abre los documentos, y decide <em>tú</em> si
alguno responde. <strong>Decide antes de mirar lo que dijo el juez.</strong>
Sé estricto: que hable del mismo tema no basta.</p>
{"".join(filas)}
<div id="resumen">Sin revisar todavía.</div>
<script>
const mias = {{}}, total = {len(filas)};
function marcar(i, valor) {{
  mias[i] = valor;
  document.getElementById('m' + i).textContent = valor === 'si' ? 'marcaste: sí' : 'marcaste: no';
  let acuerdos = 0, hechos = 0;
  for (const [k, v] of Object.entries(mias)) {{
    hechos++;
    if (document.getElementById('j' + k).value === v) acuerdos++;
  }}
  document.getElementById('resumen').textContent =
    `Revisados ${{hechos}} de ${{total}} — coincides con el juez en ${{acuerdos}}` +
    ` (${{Math.round(acuerdos / hechos * 100)}}%)`;
}}
</script></body></html>"""

    salida = Path(args.salida)
    salida.write_text(documento, encoding="utf-8")
    print(f"{len(filas)} casos en {salida}")
    print("Ábrelo en el navegador, revisa y dime el porcentaje de coincidencia final.")


if __name__ == "__main__":
    main()
