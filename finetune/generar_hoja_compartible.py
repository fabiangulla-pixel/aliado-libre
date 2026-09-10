"""Genera HTML profesional para compartir con revisores jurídicos expertos."""

import json
import pathlib
import random
import html as html_lib

# Leer los datos
auditoria = json.loads(
    pathlib.Path("finetune/eval/auditoria_metrica.json").read_text(encoding="utf-8")
)["detalle"]
candidatos = json.loads(
    pathlib.Path("finetune/eval/candidatos_prueba.json").read_text(encoding="utf-8")
)

# Seleccionar 20 casos con la misma lógica
TOPE = 5
dijo_si = [x for x in auditoria if x["responde"]]
dijo_no = [x for x in auditoria if not x["responde"]]
random.seed(7)
n_no = max(4, 20 // 4)
muestra = random.sample(dijo_si, min(20 - n_no, len(dijo_si))) + random.sample(
    dijo_no, min(n_no, len(dijo_no))
)
random.shuffle(muestra)

# Construir HTML
html_out = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Revisión Jurídica del Juez Automático</title>
<style>
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Georgia, serif;
    max-width: 900px; margin: 0 auto; padding: 1.5rem;
    line-height: 1.6; color: #2c2c2c; background: #f9f7f4;
  }
  header { border-bottom: 3px solid #7b2d26; padding-bottom: 1.5rem; margin-bottom: 2rem; }
  h1 { margin: 0 0 0.5rem 0; font-size: 1.8rem; color: #7b2d26; }
  .intro { background: #fff; padding: 1.5rem; border-left: 4px solid #7b2d26; margin-bottom: 2rem; }
  .intro p { margin: 0.5rem 0; }
  .intro strong { color: #7b2d26; }

  .formulario { background: #fff; padding: 1.5rem; border-radius: 6px; margin-bottom: 2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .campo { margin-bottom: 1rem; }
  .campo label { display: block; font-weight: bold; margin-bottom: 0.3rem; color: #333; }
  .campo input { width: 100%; padding: 0.6rem; border: 1px solid #ddd; border-radius: 4px; font-family: inherit; }
  .campo input:focus { outline: none; border-color: #7b2d26; box-shadow: 0 0 0 2px rgba(123,45,38,0.1); }

  article {
    background: #fff; border-radius: 6px; padding: 1.5rem; margin-bottom: 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1); border-left: 4px solid #ddd;
  }
  article.marcado-si { border-left-color: #2d7b38; }
  article.marcado-no { border-left-color: #d4582e; }

  h2 {
    font-size: 1.05rem; font-weight: 600; margin: 0 0 0.8rem 0;
    padding-bottom: 0.5rem; border-bottom: 1px solid #e5e5e5;
  }
  .numero {
    display: inline-block; background: #7b2d26; color: #fff;
    width: 2rem; height: 2rem; border-radius: 50%; text-align: center;
    line-height: 2rem; margin-right: 0.5rem; font-weight: bold;
  }
  .perfil { color: #666; font-size: 0.9rem; margin: 0.5rem 0 1rem 0; font-style: italic; }

  .documentos { margin: 1.5rem 0; }
  details { margin-bottom: 0.8rem; }
  summary {
    cursor: pointer; padding: 0.7rem; background: #f5f2ed;
    border-radius: 4px; font-weight: 500; user-select: none;
  }
  summary:hover { background: #ede9e2; }
  details[open] summary { background: #e5dcd1; }
  pre {
    background: #fff; border: 1px solid #ddd; padding: 0.8rem;
    border-radius: 4px; font-family: "Courier New", monospace; font-size: 0.85rem;
    white-space: pre-wrap; word-wrap: break-word; margin: 0.5rem 0 0 0;
    max-height: 300px; overflow-y: auto;
  }

  .pregunta {
    font-weight: bold; color: #2c2c2c; margin: 1.2rem 0 0.8rem 0;
    padding: 0.7rem; background: #fdf9f5; border-radius: 4px;
  }

  .botones { display: flex; gap: 0.8rem; margin: 1rem 0; }
  button {
    flex: 1; padding: 0.7rem; font-size: 1rem; font-weight: 600;
    border: 2px solid #ddd; background: #fff; border-radius: 4px;
    cursor: pointer; transition: all 0.2s;
  }
  button:hover { border-color: #7b2d26; background: #fdf9f5; }
  button.si { border-color: #2d7b38; color: #2d7b38; }
  button.si:hover { background: #f0f8f2; }
  button.si.activo { background: #2d7b38; color: #fff; }
  button.no { border-color: #d4582e; color: #d4582e; }
  button.no:hover { background: #fdf5f2; }
  button.no.activo { background: #d4582e; color: #fff; }

  .marca {
    display: inline-block; font-weight: bold; margin-left: 0.5rem;
    padding: 0.3rem 0.6rem; border-radius: 3px; font-size: 0.9rem;
  }
  .marca.si { color: #2d7b38; background: #e8f5ea; }
  .marca.no { color: #d4582e; background: #ffebee; }

  .juez {
    margin-top: 1.2rem; padding: 1rem; background: #f5f2ed;
    border-radius: 4px; border-left: 3px solid #999;
  }
  .juez summary { background: transparent; padding: 0; margin: 0; }
  .juez summary:hover { color: #7b2d26; }
  .juez p { margin: 0.5rem 0; font-size: 0.95rem; }
  .juez strong { color: #7b2d26; }

  #resumen {
    position: sticky; bottom: 0; background: #7b2d26; color: #fff;
    padding: 1rem; border-radius: 6px 6px 0 0; margin-top: 2rem;
    box-shadow: 0 -2px 8px rgba(0,0,0,0.15);
  }
  .progreso { margin-bottom: 0.8rem; font-size: 0.9rem; }
  .barra {
    height: 8px; background: rgba(255,255,255,0.3); border-radius: 4px;
    overflow: hidden; margin: 0.5rem 0;
  }
  .relleno { height: 100%; background: #4CAF50; transition: width 0.3s; }
  .botones-resumen { display: flex; gap: 0.8rem; margin-top: 1rem; }
  .botones-resumen button {
    padding: 0.6rem 1rem; background: #fff; color: #7b2d26;
    border: none; border-radius: 4px; cursor: pointer; font-weight: 600;
    flex: 1;
  }
  .botones-resumen button:hover { background: #f5f2ed; }

  footer { text-align: center; color: #999; font-size: 0.85rem; margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #ddd; }
</style>
</head><body>

<header>
  <h1>🏛️ Revisión Jurídica del Juez Automático</h1>
  <p style="margin: 0.5rem 0 0 0; color: #666;">Proyecto Aliado Libre — Validación de precisión en búsqueda legal</p>
</header>

<div class="intro">
  <p><strong>¿Qué está pasando aquí?</strong> Un sistema automático ha revisado 200 preguntas jurídicas reales. Para 100 de ellas, no encontró el documento que generó la pregunta en los primeros 5 resultados. Pero cuando se le pidió que revisara esos 5 documentos, dijo que en el <strong>78%</strong> de esos casos, <em>alguno sí respondía la pregunta</em>. Antes de publicar esa cifra, necesitamos que una persona lo verifique.</p>

  <p><strong>Tu tarea:</strong> Para cada pregunta, lee los 5 documentos que el sistema trajo y decide: ¿alguno responde la pregunta del ciudadano, aunque sea parcialmente?</p>

  <p><strong>⚠️ Importante:</strong> Decide <strong>antes</strong> de mirar lo que dijo el juez automático. Sé estricto: que hable del mismo tema no basta — tiene que contener información que responda lo que se pregunta.</p>
</div>

<div class="formulario">
  <h3 style="margin-top: 0;">Identificación del revisor</h3>
  <div class="campo">
    <label for="nombre">Tu nombre:</label>
    <input type="text" id="nombre" placeholder="Ej: María García López">
  </div>
  <div class="campo">
    <label for="email">Email (opcional):</label>
    <input type="email" id="email" placeholder="ej@example.com">
  </div>
  <div class="campo">
    <label for="especializacion">Especialización (opcional):</label>
    <input type="text" id="especializacion" placeholder="Ej: Derecho Civil, Tributario, Laboral...">
  </div>
</div>

"""

# Agregar casos
for i, caso in enumerate(muestra, 1):
    fuente = next((c for c in candidatos if c["consulta"] == caso["consulta"]), None)
    if not fuente:
        continue

    docs_html = "".join(
        f"<details><summary>Documento {j}</summary><pre>{html_lib.escape(c.get('texto', '')[:1500])}</pre></details>"
        for j, c in enumerate(fuente.get("candidatos", [])[:TOPE], 1)
    )
    veredicto = "SÍ responde" if caso["responde"] else "NO responde"
    html_out += f"""
<article id="art{i}">
  <h2><span class="numero">{i}</span> {html_lib.escape(caso["consulta"][:100])}</h2>
  <p class="perfil">Perfil: {html_lib.escape(caso["perfil"])}</p>

  <div class="documentos">
    <p style="font-weight: 600; color: #7b2d26;">Documentos que el buscador trajo:</p>
    {docs_html}
  </div>

  <p class="pregunta">¿Alguno de esos cinco documentos responde la pregunta?</p>

  <div class="botones">
    <button onclick="marcar({i}, 'si')" id="btn{i}si" class="si">✓ Sí responde</button>
    <button onclick="marcar({i}, 'no')" id="btn{i}no" class="no">✗ No responde</button>
    <span id="m{i}" class="marca"></span>
  </div>

  <details class="juez">
    <summary>📋 Ver veredicto del juez automático (antes de decidir, ¡no hagas clic!)</summary>
    <p><strong>{veredicto}</strong></p>
    <p style="font-size: 0.9rem; color: #666; margin-top: 0.5rem;">{html_lib.escape(caso["razon"])}</p>
    <input type="hidden" id="j{i}" value="{'si' if caso['responde'] else 'no'}">
  </details>
</article>
"""

html_out += """
</body>
<div id="resumen">
  <div class="progreso">Progreso: <strong id="prog">0/20</strong></div>
  <div class="barra"><div class="relleno" id="relleno" style="width: 0%"></div></div>
  <div id="estadisticas" style="font-size: 0.9rem; margin: 0.8rem 0;">Sí: <strong id="si">0</strong> | No: <strong id="no">0</strong> | Acuerdo con juez: <strong id="acuerdo">—</strong></div>
  <div class="botones-resumen">
    <button onclick="descargarJSON()">💾 Descargar resultados (JSON)</button>
    <button onclick="copiarResumen()">📋 Copiar resumen</button>
  </div>
</div>

<footer>
  <p>Aliado Libre • Revisión humana de juez automático • Septiembre 2026</p>
</footer>

<script>
const mias = {}, total = 20;
function marcar(i, valor) {
  mias[i] = valor;
  document.getElementById(`art${i}`).classList.toggle("marcado-si", valor === "si");
  document.getElementById(`art${i}`).classList.toggle("marcado-no", valor === "no");
  document.getElementById(`btn${i}si`).classList.toggle("activo", valor === "si");
  document.getElementById(`btn${i}no`).classList.toggle("activo", valor === "no");

  if (valor === "si") {
    document.getElementById(`m${i}`).textContent = "✓ Marcado";
    document.getElementById(`m${i}`).className = "marca si";
  } else {
    document.getElementById(`m${i}`).textContent = "✗ Marcado";
    document.getElementById(`m${i}`).className = "marca no";
  }
  actualizar();
}

function actualizar() {
  const n = Object.keys(mias).length;
  document.getElementById("prog").textContent = `${n}/20`;
  document.getElementById("relleno").style.width = `${n * 5}%`;

  const siCount = Object.values(mias).filter(x => x === "si").length;
  const noCount = Object.values(mias).filter(x => x === "no").length;
  document.getElementById("si").textContent = siCount;
  document.getElementById("no").textContent = noCount;

  if (n > 0) {
    const juez = {};
    for (let i = 1; i <= 20; i++) {
      const el = document.getElementById(`j${i}`);
      if (el) juez[i] = el.value;
    }
    const aciertos = Object.keys(mias).filter(i => mias[i] === juez[i]).length;
    const pct = Math.round(aciertos / n * 100);
    document.getElementById("acuerdo").textContent = `${aciertos}/${n} (${pct}%)`;
  }
}

function descargarJSON() {
  const nombre = document.getElementById("nombre").value || "Anónimo";
  const resultado = {
    revisor: nombre,
    email: document.getElementById("email").value || null,
    especializacion: document.getElementById("especializacion").value || null,
    fecha: new Date().toISOString(),
    respuestas: mias,
    resumen: {
      total_revisados: Object.keys(mias).length,
      si: Object.values(mias).filter(x => x === "si").length,
      no: Object.values(mias).filter(x => x === "no").length
    }
  };

  const blob = new Blob([JSON.stringify(resultado, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `revision_${nombre.replace(/\\s+/g, "_")}_${new Date().toISOString().split("T")[0]}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function copiarResumen() {
  const nombre = document.getElementById("nombre").value || "Anónimo";
  const si = Object.values(mias).filter(x => x === "si").length;
  const no = Object.values(mias).filter(x => x === "no").length;
  const n = si + no;
  const txt = `Revisor: ${nombre}\\nCasos: ${n}/20\\nSí responde: ${si}\\nNo responde: ${no}`;
  navigator.clipboard.writeText(txt).then(() => alert("Copiado al portapapeles"));
}

document.addEventListener("DOMContentLoaded", actualizar);
</script>
</html>
"""

pathlib.Path("finetune/eval/revision_juridica_compartible.html").write_text(
    html_out, encoding="utf-8"
)
print("✓ HTML profesional para compartir creado")
print(f"  Archivo: finetune/eval/revision_juridica_compartible.html")
print(f"  Tamaño: {len(html_out.encode()) // 1024} KB")
print("  Características:")
print("    • Instrucciones claras en la parte superior")
print("    • Campo para identificar al revisor (nombre, email, especialización)")
print("    • 20 casos con 5 documentos cada uno")
print("    • Veredicto del juez automático oculto (details)")
print("    • Resumen con progreso en tiempo real")
print("    • Descarga resultados como JSON")
print("    • Copiar resumen al portapapeles")
