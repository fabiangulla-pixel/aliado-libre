#!/usr/bin/env python3
"""Hoja de revisión humana: ¿las abstenciones del enrutador son correctas?

Hallazgo del 29-sep-2026: el puntaje del mejor resultado es casi binario —
0,0167 si lo encontró un solo motor (1/60 del RRF) o ≥0,026 si coinciden los
dos—, así que `UMBRAL_ABSTENCION = 0,020` no mide relevancia: mide si la
búsqueda léxica coincide con la semántica. En el piloto la app se abstiene en
47 de 100 consultas, y en lenguaje llano casi nunca coinciden los dos motores.

Solo en 4 de esas 47 estaba el documento ancla, pero la métrica por ancla
subestima (12-sep: el 81% de los "fallos" respondían con otra norma). Decidir el
umbral exige juzgar si ALGUNO de los cinco resultados responde. Eso lo decide
una persona, no un juez de IA: ver [[feedback_verdad_de_referencia_humana_o_no_hay_metrica]].

Uso:  .venv/Scripts/python.exe finetune/eval/revisar_abstenciones.py
Abre: finetune/eval/revision_abstenciones.html (no se versiona: trae el banco)
"""

from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))

BANCO = RAIZ / "finetune" / "eval" / "banco_piloto_100.json"
SALIDA = RAIZ / "finetune" / "eval" / "revision_abstenciones.html"


def main() -> None:
    from index.buscar import IndiceBusqueda
    from index.enrutador import decidir

    casos = json.loads(BANCO.read_text(encoding="utf-8"))
    indice = IndiceBusqueda()
    filas = []
    for c in casos:
        resultados = indice.buscar(c["consulta"], k=5)
        if decidir(resultados, hay_clave_externa=True).responde:
            continue
        filas.append((c, resultados))

    bloques = []
    for n, (c, resultados) in enumerate(filas, 1):
        items = "".join(
            f"<li><b>{html.escape(r.get('titulo_documento') or '')}</b> "
            f"<small>({html.escape(r['vigencia']['estado'])})</small>"
            f"<details><summary>{html.escape((r.get('texto') or '')[:280])}…</summary>"
            f"<pre>{html.escape(r.get('texto') or '')}</pre></details></li>"
            for r in resultados
        )
        bloques.append(
            f'<section data-id="{html.escape(c["id"])}"><h2>{n}. «{html.escape(c["consulta"])}»</h2>'
            f"<p class=perfil>{html.escape(c['perfil'])} · {html.escape(c['tipo'])}</p><ol>{items}</ol>"
            '<p><button data-v="si">Alguno responde</button> <button data-v="no">Ninguno responde</button>'
            ' <span class="marca"></span></p></section>'
        )

    SALIDA.write_text(
        f"""<!doctype html><meta charset="utf-8"><title>Revisión de abstenciones</title>
<style>body{{font:16px/1.5 system-ui;max-width:900px;margin:auto;padding:16px}}
section{{border-top:1px solid #ccc;padding:8px 0}}.perfil{{color:#666}}
pre{{white-space:pre-wrap;background:#f6f6f6;padding:8px}}button{{padding:6px 12px}}
#total{{position:sticky;top:0;background:#fffbe6;padding:8px;border:1px solid #e6d27a}}</style>
<h1>¿La app hizo bien en NO responder?</h1>
<p>La app se abstuvo en estas {len(filas)} consultas. Para cada una: ¿algún resultado contiene
una norma o sentencia que le sirva a quien preguntó? No hace falta que sea perfecta; basta con
que un abogado la señalaría como el lugar donde mirar.</p>
<div id=total>Revisados 0 de {len(filas)}</div>
{"".join(bloques)}
<script>
const v={{}};
document.querySelectorAll('button').forEach(b=>b.onclick=()=>{{
  const s=b.closest('section'); v[s.dataset.id]=b.dataset.v;
  s.querySelector('.marca').textContent = b.dataset.v==='si' ? '✔ responde' : '✘ no responde';
  const n=Object.keys(v).length, si=Object.values(v).filter(x=>x==='si').length;
  document.getElementById('total').textContent =
    `Revisados ${{n}} de {len(filas)} — en ${{si}} la abstención fue un ERROR (había respuesta)`;
}});
</script>""",
        encoding="utf-8",
    )
    print(f"{len(filas)} abstenciones -> {SALIDA}")


if __name__ == "__main__":
    main()
