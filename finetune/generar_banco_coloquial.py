"""Construye un banco de consultas COLOQUIALES ancladas a fragmentos reales.

Por qué existe: el banco de 150 preguntas (finetune/eval/banco_prueba.json) lo
generó un LLM *a partir de los fragmentos*, así que heredó su vocabulario
jurídico. Mide bien la redacción de respuestas, pero es ciego al fallo real del
producto: un cliente no escribe "recolección y transporte de residuos
originados por la poda de árboles", escribe "quien recoge las ramas que corté".
Con el banco viejo, la recuperación medida describe a un abogado consultando, no a un
ciudadano.

Cómo se ancla la verdad de referencia: cada consulta se genera A PARTIR DE un
fragmento concreto, así que ese fragmento es, por construcción, una respuesta
correcta. No hace falta juez: la métrica es si la búsqueda lo devuelve o no.
Se acepta como acierto cualquier fragmento del MISMO documento (documento_id),
porque el corpus tiene normas repetidas entre fuentes y trocear un artículo en
varios fragmentos es arbitrario respecto a la pregunta.

Ocho perfiles de usuario, elegidos para cubrir el rango real de quien
consultaría legislación colombiana gratuita — no ocho formas de decir lo mismo,
sino ocho maneras distintas de fallar.

Uso:
    ANTHROPIC_API_KEY=... ./venv/Scripts/python.exe finetune/generar_banco_coloquial.py [n_fragmentos]
"""

from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CHROMA = RAIZ.parent / "index" / "chroma_db" / "chroma.sqlite3"
SALIDA = RAIZ / "eval" / "banco_coloquial.json"
MODELO = "claude-sonnet-4-5"
SEMILLA = 20260904

# Proporcional al corpus, pero con suelo para las fuentes chicas: sic y
# superfinanciera son <1% y desaparecerían de un muestreo puramente
# proporcional, justo las dos de vocabulario más especializado.
CUOTAS = {
    "legalize_co_github": 0.30,
    "gestor_normativo": 0.20,
    "dian": 0.14,
    "corte_constitucional": 0.14,
    "supersociedades": 0.10,
    "sic": 0.08,
    "superfinanciera": 0.04,
}

PERFILES = {
    "baja_alfabetizacion": (
        "Persona con escolaridad básica incompleta. Escribe sin tildes, con faltas de "
        "ortografía, sin signos de interrogación de apertura, frases cortas y cortadas. "
        "No conoce ni una palabra técnica."
    ),
    "adulto_mayor_informal": (
        "Adulto mayor, habla con rodeos y cortesía ('buenas, una pregunta...'), cuenta "
        "primero su situación personal y la pregunta llega al final, larga y difusa."
    ),
    "ciudadano_medio": (
        "Adulto con bachillerato, escribe correctamente pero en lenguaje corriente. "
        "Ninguna palabra jurídica; describe el problema como se lo contaría a un amigo."
    ),
    "comerciante_practico": (
        "Dueño de un negocio pequeño. Pregunta orientada al resultado práctico: si puede "
        "o no puede, cuánto le cuesta, qué le pasa si no lo hace. Usa jerga comercial, "
        "no jurídica."
    ),
    "semi_tecnico_impreciso": (
        "Persona con algo de formación (estudiante, auxiliar administrativo). Intenta usar "
        "palabras jurídicas pero las usa MAL o aproximadas: confunde decreto con ley, "
        "'demanda' con 'tutela', inventa nombres de normas."
    ),
    "mensaje_telegrafico": (
        "Escribe como en WhatsApp o dictado por voz: sin puntuación, minúsculas, muy corto "
        "(entre 3 y 10 palabras), a veces solo palabras clave sueltas."
    ),
    "con_ruido_irrelevante": (
        "Mezcla la pregunta con datos personales que no vienen al caso (nombre de su "
        "empresa, su ciudad, su edad, cuánto lleva esperando) y con carga emocional o "
        "urgencia. La pregunta real está enterrada en el ruido."
    ),
    "abogado_junior": (
        "Profesional del derecho: vocabulario técnico correcto y preciso. Es el GRUPO DE "
        "CONTROL — si la búsqueda tampoco funciona aquí, el problema no es el registro "
        "del lenguaje."
    ),
}

PROMPT = """Vas a ayudar a construir un banco de pruebas para un buscador de legislación colombiana.

Te doy un fragmento REAL de una norma o sentencia colombiana. Tu tarea: escribir {n} consultas
distintas que una persona haría a un buscador legal y cuya respuesta correcta esté en ESTE
fragmento — una consulta por cada perfil de usuario que te listo.

Fragmento (fuente: {fuente} — {identificador}):
\"\"\"
{texto}
\"\"\"

Perfiles:
{perfiles}

Reglas estrictas:
- Cada consulta debe poder responderse con este fragmento. Si el fragmento es puramente
  procedimental o no da información útil a un ciudadano, dilo con {{"inservible": true}} y nada más.
- NO copies frases del fragmento. Ese es justamente el error que este banco existe para evitar:
  el usuario no conoce el texto de la norma.
- Escribe en español de Colombia, con giros locales cuando el perfil lo pida.
- Respeta de verdad cada perfil: el de baja alfabetización debe verse distinto del de abogado.
- No menciones el número de la norma salvo en el perfil de abogado (un ciudadano no lo sabe).

Responde SOLO con un JSON: {{"consultas": {{"nombre_perfil": "la consulta", ...}}}}"""


def _muestrear(n_total: int) -> list[dict]:
    con = sqlite3.connect(f"file:{CHROMA}?mode=ro", uri=True)
    aleatorio = random.Random(SEMILLA)
    muestras: list[dict] = []

    for fuente, cuota in CUOTAS.items():
        objetivo = max(1, round(n_total * cuota))
        filas = con.execute(
            "SELECT id FROM embedding_metadata WHERE key='fuente' AND string_value=?", (fuente,)
        ).fetchall()
        if not filas:
            print(f"  aviso: sin fragmentos para {fuente}")
            continue
        ids = [f[0] for f in filas]
        aleatorio.shuffle(ids)

        tomados = 0
        for fila_id in ids:
            if tomados >= objetivo:
                break
            campos = dict(
                con.execute(
                    "SELECT key, string_value FROM embedding_metadata WHERE id=?", (fila_id,)
                ).fetchall()
            )
            texto = (campos.get("chroma:document") or "").strip()
            # fragmentos muy cortos no dan para ocho preguntas distintas
            if len(texto) < 600:
                continue
            frag_id = con.execute("SELECT embedding_id FROM embeddings WHERE id=?", (fila_id,)).fetchone()
            if not frag_id:
                continue
            muestras.append(
                {
                    "fragmento_id": frag_id[0],
                    "documento_id": campos.get("documento_id"),
                    "identificador_documento": campos.get("identificador_documento"),
                    "titulo_documento": campos.get("titulo_documento"),
                    "fuente": fuente,
                    "texto": texto[:4000],
                }
            )
            tomados += 1
        print(f"  {fuente}: {tomados} fragmentos")
    return muestras


def main() -> None:
    n_total = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    hilos = int(sys.argv[2]) if len(sys.argv) > 2 else 8

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Falta ANTHROPIC_API_KEY en el entorno.")
    import anthropic

    cliente = anthropic.Anthropic(api_key=api_key)

    print(f"Muestreando {n_total} fragmentos estratificados por fuente...")
    muestras = _muestrear(n_total)
    print(f"Total muestreado: {len(muestras)}")

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    banco = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else []
    ya = {c["fragmento_id"] for c in banco}
    if ya:
        print(f"Reanudando: {len(banco)} consultas de {len(ya)} fragmentos ya generados.")

    perfiles_texto = "\n".join(f"- {n}: {d}" for n, d in PERFILES.items())
    pendientes = [m for m in muestras if m["fragmento_id"] not in ya]
    inservibles = 0
    candado = threading.Lock()
    hechos = 0

    def procesar(m: dict):
        prompt = PROMPT.format(
            n=len(PERFILES),
            fuente=m["fuente"],
            identificador=m["identificador_documento"] or "?",
            texto=m["texto"],
            perfiles=perfiles_texto,
        )
        try:
            r = cliente.messages.create(
                model=MODELO, max_tokens=1500, messages=[{"role": "user", "content": prompt}]
            )
            texto = "".join(b.text for b in r.content if hasattr(b, "text"))
            bloque = re.search(r"\{.*\}", texto, re.DOTALL)
            return m, (json.loads(bloque.group(0)) if bloque else None)
        except Exception as e:  # noqa: BLE001 - una muestra mala no debe tumbar el lote
            print(f"  error en {m['fragmento_id']}: {type(e).__name__}: {str(e)[:100]}")
            return m, None

    # En serie son ~35s por fragmento y el lote no cabe en la ventana de
    # trabajo disponible. El cuello es la latencia de la API, no la CPU.
    with ThreadPoolExecutor(max_workers=hilos) as pool:
        futuros = [pool.submit(procesar, m) for m in pendientes]
        for futuro in as_completed(futuros):
            m, datos = futuro.result()
            with candado:
                hechos += 1
                if not datos or datos.get("inservible") or not datos.get("consultas"):
                    inservibles += 1
                else:
                    for perfil, consulta in datos["consultas"].items():
                        if perfil not in PERFILES or not isinstance(consulta, str):
                            continue
                        if not consulta.strip():
                            continue
                        banco.append(
                            {
                                "consulta": consulta.strip(),
                                "perfil": perfil,
                                "fragmento_id": m["fragmento_id"],
                                "documento_id": m["documento_id"],
                                "identificador_documento": m["identificador_documento"],
                                "fuente": m["fuente"],
                            }
                        )
                    SALIDA.write_text(json.dumps(banco, ensure_ascii=False, indent=2), encoding="utf-8")
                if hechos % 10 == 0 or hechos == len(pendientes):
                    print(f"  [{hechos}/{len(pendientes)}] {len(banco)} consultas")

    print(f"\nListo: {len(banco)} consultas en {SALIDA}")
    print(f"Fragmentos descartados por inservibles: {inservibles}")


if __name__ == "__main__":
    main()
