#!/usr/bin/env python3
import html as _html
import json
import pathlib


def escapar(texto: str) -> str:
    return _html.escape(texto or "")


casos_data = json.loads(pathlib.Path("finetune/eval/20_casos_regenerados.json").read_text(encoding="utf-8"))
casos = casos_data["casos"]

# Los documentos salen del propio JSON regenerado, o sea del indice vigente.
# Antes se leian de candidatos_prueba.json, que son los candidatos del indice
# VIEJO: la hoja mezclaba una cabecera del indice nuevo con documentos de otro.

# Construir casos con documentos
casos_con_docs = []
for i, caso in enumerate(casos, 1):
    docs = caso.get("documentos", [])[:5]

    docs_html = ""
    for d in docs:
        texto = escapar(d.get("texto", "")[:1500])
        cabecera = escapar(f"{d.get('identificador', '')} - {d.get('titulo', '')}"[:110])
        docs_html += (
            f"<details><summary>Documento {d.get('orden', '?')}: {cabecera}</summary>"
            f"<pre>{texto}</pre></details>"
        )
    if not docs_html:
        docs_html = "<p class='aviso'>SIN DOCUMENTOS: la busqueda no devolvio nada para esta consulta.</p>"

    casos_con_docs.append(
        {
            "num": i,
            "consulta": caso["consulta"],
            "fuente": caso["fuente"],
            "identificador": caso["identificador"],
            "documento": caso["documento"],
            "fragmento": caso["fragmento_preview"][:300] + "..."
            if len(caso["fragmento_preview"]) > 300
            else caso["fragmento_preview"],
            "docs_html": docs_html,
            "longitud": caso["longitud_fragmento"],
        }
    )

casos_json = json.dumps(
    [
        {
            "num": c["num"],
            "consulta": c["consulta"],
            "fuente": c["fuente"],
            "identificador": c["identificador"],
        }
        for c in casos_con_docs
    ]
)

html_casos = "\n".join(
    [
        f"""<article id="art{c["num"]}">
    <h2><span class="num">{c["num"]}</span>{c["consulta"][:90]}</h2>
    <p class="perfil">Pregunta</p>
    <div class="fuente-info">
      <strong>{c["fuente"].replace("_", " ")} - {c["identificador"]}</strong><br>
      <small>{c["documento"]}</small>
    </div>
    <div style="background: #f9f7f3; padding: 0.8rem; border-radius: 3px; margin-bottom: 0.8rem;">
      <p style="margin: 0; font-size: 0.9rem; line-height: 1.5;">{c["fragmento"]}</p>
      <p style="margin: 0.4rem 0 0; font-size: 0.75rem; color: #999;">[{c["longitud"]} caracteres]</p>
    </div>
    <div class="docs">
      <p class="docs-titulo">Los 5 documentos que devolvio la busqueda:</p>
      {c["docs_html"]}
    </div>
    <div class="btns">
      <button onclick="marcar({c["num"]}, 'si')">Si responde</button>
      <button onclick="marcar({c["num"]}, 'no')" class="no">No responde</button>
      <span id="m{c["num"]}" class="marca"></span>
    </div>
  </article>"""
        for c in casos_con_docs
    ]
)

html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Revision Juridica - 20 Casos Limpios v2</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: Georgia, serif; max-width: 950px; margin: 0 auto; padding: 1.5rem; line-height: 1.6; color: #2c2c2c; background: #faf8f5; }}
    header {{ border-bottom: 3px solid #7b2d26; padding-bottom: 1rem; margin-bottom: 1.5rem; }}
    h1 {{ margin: 0 0 0.2rem 0; color: #7b2d26; font-size: 1.6rem; }}
    .intro {{ background: white; padding: 1.2rem; border-left: 4px solid #7b2d26; margin-bottom: 1.5rem; }}
    .intro p {{ margin: 0.5rem 0; }}
    .formulario {{ background: white; padding: 1.2rem; border-radius: 4px; margin-bottom: 1.5rem; }}
    .campo {{ margin-bottom: 0.8rem; }}
    label {{ display: block; font-weight: bold; font-size: 0.9rem; margin-bottom: 0.2rem; }}
    input {{ width: 100%; padding: 0.5rem; border: 1px solid #ddd; border-radius: 3px; font-size: 0.95rem; }}
    #casos {{ margin: 1.5rem 0; }}
    article {{ background: white; padding: 1.2rem; margin-bottom: 1.2rem; border-left: 4px solid #ddd; border-radius: 3px; }}
    article.si {{ border-left-color: #2d7b38; }}
    article.no {{ border-left-color: #d4582e; }}
    h2 {{ font-size: 0.95rem; font-weight: 600; margin: 0 0 0.6rem 0; padding-bottom: 0.4rem; border-bottom: 1px solid #eee; }}
    .num {{ background: #7b2d26; color: white; width: 24px; height: 24px; border-radius: 50%; text-align: center; line-height: 24px; display: inline-block; margin-right: 0.4rem; font-weight: bold; font-size: 0.85rem; }}
    .perfil {{ color: #666; font-size: 0.85rem; font-style: italic; margin: 0.5rem 0 0.8rem 0; }}
    .fuente-info {{ background: #f5f2ed; padding: 0.6rem; border-radius: 3px; font-size: 0.85rem; margin-bottom: 0.8rem; }}
    .fuente-info strong {{ color: #7b2d26; }}
    details {{ margin: 0.8rem 0; }}
    summary {{ cursor: pointer; padding: 0.6rem; background: #f5f2ed; border-radius: 3px; font-weight: 500; font-size: 0.9rem; }}
    pre {{ background: #fff; border: 1px solid #ddd; padding: 0.7rem; font-size: 0.8rem; max-height: 200px; overflow-y: auto; margin: 0.4rem 0; }}
    .btns {{ display: flex; gap: 0.6rem; margin: 0.8rem 0; }}
    button {{ flex: 1; padding: 0.6rem; font-size: 0.9rem; font-weight: 600; border: 2px solid #ddd; background: white; border-radius: 3px; cursor: pointer; transition: 0.2s; }}
    button:hover {{ border-color: #7b2d26; background: #fdf9f5; }}
    button.on {{ background: #2d7b38; color: white; border-color: #2d7b38; }}
    button.no.on {{ background: #d4582e; color: white; border-color: #d4582e; }}
    .marca {{ font-weight: bold; color: #2d7b38; margin-left: 0.4rem; }}
    #resumen {{ position: sticky; bottom: 0; background: #7b2d26; color: white; padding: 0.8rem; margin-top: 1.5rem; border-radius: 3px 3px 0 0; font-size: 0.9rem; }}
    footer {{ text-align: center; color: #999; font-size: 0.8rem; margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #ddd; }}
  </style>
</head>
<body>

<header>
  <h1>Revision Juridica - 20 Casos Limpios</h1>
  <p style="color: #666; margin: 0.2rem 0 0 0;">Aliado Libre - Auditoria v2 (fragmentos verificados sin ceremonial)</p>
</header>

<div class="intro">
  <p><strong>Tu tarea:</strong> Lee los documentos de cada caso y decide si alguno RESPONDE la pregunta.</p>
  <p><strong>Importante:</strong> Decide ANTES de revisar el texto. Se estricto: que mencione el tema no basta - tiene que responder.</p>
</div>

<div class="formulario">
  <h3 style="margin-top: 0;">Sobre ti</h3>
  <div class="campo">
    <label for="nombre">Nombre:</label>
    <input type="text" id="nombre" placeholder="Tu nombre completo">
  </div>
  <div class="campo">
    <label for="email">Email:</label>
    <input type="email" id="email" placeholder="tu@email.com">
  </div>
  <div class="campo">
    <label for="esp">Especialidad (opcional):</label>
    <input type="text" id="esp" placeholder="Ej: Derecho Civil, Laboral...">
  </div>
</div>

<div id="casos">
{html_casos}
</div>

<div id="resumen">
  <strong id="prog">0/20 revisados</strong>
  <span id="acuerdo" style="margin-left: 1rem;"></span>
  <br><button style="margin-top: 0.6rem; padding: 0.5rem 1rem; background: white; color: #7b2d26; border: none; border-radius: 3px; cursor: pointer; font-weight: bold;" onclick="descargar()">Descargar JSON</button>
</div>

<footer>
  <p>Aliado Libre - Auditoria de recuperacion v2 (septiembre 2026)</p>
</footer>

<script>
const respuestas = {{}};

window.marcar = function(i, val) {{
  respuestas[i] = val;
  const art = document.getElementById("art" + i);
  art.classList.remove("si", "no");
  art.classList.add(val);
  document.getElementById("m" + i).textContent = val === "si" ? "S" : "N";
  actualizar();
}};

function actualizar() {{
  const n = Object.keys(respuestas).length;
  document.getElementById("prog").textContent = n + "/20 revisados";
}}

function descargar() {{
  const resultado = {{
    revisor: document.getElementById("nombre").value || "Anonimo",
    email: document.getElementById("email").value || null,
    especializacion: document.getElementById("esp").value || null,
    fecha: new Date().toISOString(),
    respuestas: respuestas,
    resumen: {{ total: Object.keys(respuestas).length }}
  }};
  const blob = new Blob([JSON.stringify(resultado, null, 2)]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "revision_" + (document.getElementById("nombre").value || "anonimo").replace(/\\s+/g, "_") + "_" + new Date().toISOString().split("T")[0] + ".json";
  a.click();
}}
</script>

</body>
</html>"""

pathlib.Path("finetune/eval/revision_juridica_limpia_v2.html").write_text(html, encoding="utf-8")
print(f"OK - HTML generado: revision_juridica_limpia_v2.html ({len(html) / 1024:.0f} KB)")
