#!/usr/bin/env python3
"""Etapa 2 del piloto: contrasta lo que responde la aplicación contra el banco.

La idea del piloto es que Claude redactó, a partir del texto real del corpus,
100 consultas con la respuesta que un usuario necesita (`banco_piloto_100.json`)
y aquí se mide qué tan cerca queda la aplicación.

**Casi todo lo que se mide aquí es determinista.** Esa fue la condición para que
el piloto sirva de algo: si quien escribe el banco es también quien juzga las
respuestas, lo que se mide es su consistencia, no la verdad. Por eso las
métricas son comprobaciones, no opiniones:

  recuperacion   ¿alguno de los 5 primeros resultados viene del documento
                 anclado? (igual criterio que `medir_recuperacion.py`)
  cita_literal   ¿lo que la respuesta pone entre «» aparece LITERALMENTE en los
                 fragmentos que se le pasaron? Es la prueba de alucinación más
                 barata que existe y no necesita juez.
  formato        ¿la respuesta trae las tres partes pedidas (norma, cita,
                 explicación)?
  abstencion     en los casos `no_cubierto`, ¿dijo que no sabe en vez de
                 inventar?
  vigencia       en los casos `trampa_derogada`, ¿advirtió que la norma está
                 derogada o es inexequible?

Lo único que queda a juicio humano es si la redacción le sirve al usuario, y
para eso están `respuesta_referencia` y la hoja de revisión: no se resuelve
aquí.

SIN --ejecutar no gasta un peso: estima el costo y para.

Uso:
    ./.venv/Scripts/python.exe finetune/eval/correr_piloto.py            # estima
    ./.venv/Scripts/python.exe finetune/eval/correr_piloto.py --ejecutar # gasta
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ))

BANCO = RAIZ / "finetune" / "eval" / "banco_piloto_100.json"
SALIDA = RAIZ / "finetune" / "eval" / "resultado_piloto.json"

TOPE = 5
# Cuántos fallos seguidos desde el arranque bastan para dar la corrida por rota.
UMBRAL_ABORTO = 5
PATRON_CITA = re.compile(r"«([^»]{15,})»")
PATRON_NORMA = re.compile(
    r"(?i)\b(?:ley|decreto|resoluci[oó]n|circular|oficio|concepto|sentencia|auto|art[ií]culo)\b"
)
MARCAS_ABSTENCION = (
    "no encontré información suficiente",
    "no encontre informacion suficiente",
    "no está en el índice",
    "no esta en el indice",
    "no está indexad",
    "no esta indexad",
)
MARCAS_VIGENCIA = (
    "derogad",
    "inexequible",
    "no compilado",
    "sustituid",
    "ya no está vigente",
    "ya no esta vigente",
    "no sigue vigente",
    "caduc",
)


def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    for a, b in (("“", '"'), ("”", '"'), ("«", '"'), ("»", '"'), ("’", "'"), ("‘", "'")):
        t = t.replace(a, b)
    return re.sub(r"[\s ]+", " ", t).lower().strip()


def cita_esta_en_los_fragmentos(respuesta: str, fragmentos: list[dict]) -> tuple[int, int]:
    """Cuántas de las citas entre «» aparecen de verdad en el contexto.

    Se comprueba contra los fragmentos que se le PASARON al modelo, no contra
    todo el corpus: citar bien algo que no estaba en el contexto seguiría
    siendo inventar, aunque por casualidad exista en otra parte.
    """
    contexto = normalizar(" ".join(f.get("texto", "") for f in fragmentos))
    citas = PATRON_CITA.findall(respuesta or "")
    if not citas:
        return 0, 0
    buenas = 0
    for c in citas:
        n = normalizar(c)
        # los recortes con [...] se verifican por trozos
        trozos = [t.strip() for t in n.split("[...]") if len(t.strip()) >= 15]
        if trozos and all(t in contexto for t in trozos):
            buenas += 1
    return buenas, len(citas)


def tiene_formato(respuesta: str) -> bool:
    r = respuesta or ""
    return bool(PATRON_NORMA.search(r)) and bool(PATRON_CITA.search(r)) and len(r) > 180


def se_abstuvo(respuesta: str) -> bool:
    n = normalizar(respuesta or "")
    return any(normalizar(m) in n for m in MARCAS_ABSTENCION)


def advirtio_vigencia(respuesta: str) -> bool:
    n = normalizar(respuesta or "")
    return any(normalizar(m) in n for m in MARCAS_VIGENCIA)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ejecutar", action="store_true", help="gasta de verdad; sin esto solo estima")
    ap.add_argument("--proveedor", default="claude")
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()

    from index import costos
    from index.buscar import IndiceBusqueda
    from index.proveedores import MODELOS_POR_DEFECTO, generar
    from index.responder import PROMPT_SISTEMA, construir_prompt

    modelo = args.modelo or MODELOS_POR_DEFECTO[args.proveedor]
    casos = json.loads(BANCO.read_text(encoding="utf-8"))
    if args.limite:
        casos = casos[: args.limite]

    print(f"{len(casos)} consultas | proveedor {args.proveedor} | modelo {modelo}")
    print("Cargando índice...")
    t0 = time.time()
    indice = IndiceBusqueda()
    print(f"Índice listo en {time.time() - t0:.0f}s\n")

    # --- Paso 1: recuperación (gratis) y armado de los prompts ---
    recuperado = []
    total_usd_estimado = 0.0
    for i, c in enumerate(casos, 1):
        res = indice.buscar(c["consulta"], k=TOPE)
        prompt = construir_prompt(c["consulta"], res)
        total_usd_estimado += costos.estimar(prompt, modelo).usd
        recuperado.append((c, res, prompt))
        if i % 20 == 0:
            print(f"  recuperados {i}/{len(casos)}")

    print("\n" + "=" * 72)
    print(
        f"COSTO ESTIMADO de la etapa de redacción: {total_usd_estimado:.2f} USD "
        f"(~{total_usd_estimado * costos.TRM_APROXIMADA:,.0f} COP)"
    )
    print("=" * 72)

    if not args.ejecutar:
        # La recuperación ya se puede medir sin gastar nada.
        informe_recuperacion(recuperado)
        print("\nNo se llamó a ninguna API. Añade --ejecutar para redactar las respuestas.")
        return 0

    clave = ""
    if args.proveedor != "ollama":
        from finetune.clave_api import leer_clave

        clave = leer_clave(obligatoria=False) or ""
        if not clave:
            print("Falta la clave de API: ~/.aliado_libre/credenciales.json o la variable de entorno.")
            return 1

    filas = []
    usd_real = 0.0
    fallos = 0
    primer_fallo = ""
    for i, (c, res, prompt) in enumerate(recuperado, 1):
        try:
            r = generar(prompt, PROMPT_SISTEMA, args.proveedor, clave, modelo)
            texto = r.texto
            usd_real += costos.liquidar(r.usage, modelo).usd
        except Exception as e:  # noqa: BLE001
            texto = ""
            fallos += 1
            if not primer_fallo:
                primer_fallo = f"{type(e).__name__}: {e}"
            print(f"  [{c['id']}] fallo: {type(e).__name__}")
            # Una respuesta vacía puntúa 0 en formato, 0 en citas y 0 en
            # abstención, así que una corrida que falla entera IMPRIME UN
            # INFORME DE CEROS QUE PARECE UNA MEDICIÓN. Pasó el 12-sep-2026:
            # las 100 llamadas murieron por un argumento que el SDK ya no
            # acepta y el informe dijo "formato 0%, abstención 0%" como si se
            # hubiera medido algo. Si falla el arranque entero, se aborta.
            if fallos >= UMBRAL_ABORTO and fallos == i:
                print(
                    f"\nABORTADO: las {fallos} primeras llamadas fallaron.\n"
                    f"  Primer error: {primer_fallo}\n"
                    "  No se publica un informe: un informe de ceros no es una medición."
                )
                return 1
        buenas, citas = cita_esta_en_los_fragmentos(texto, res)
        filas.append(
            {
                **{k: c[k] for k in ("id", "perfil", "tipo", "tema", "consulta")},
                "documento_id": c.get("documento_id"),
                "norma_esperada": c.get("norma_esperada"),
                "respuesta_referencia": c["respuesta_referencia"],
                "respuesta_app": texto,
                "documentos_recuperados": [r_.get("documento_id") for r_ in res],
                "acierto_recuperacion": acierta(res, c),
                "citas_totales": citas,
                "citas_literales": buenas,
                "formato_ok": tiene_formato(texto),
                "se_abstuvo": se_abstuvo(texto),
                "advirtio_vigencia": advirtio_vigencia(texto),
            }
        )
        if i % 10 == 0:
            print(f"  redactadas {i}/{len(casos)}  ({usd_real:.2f} USD)")

    SALIDA.write_text(
        json.dumps({"modelo": modelo, "usd": usd_real, "detalle": filas}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    informe(filas, usd_real)
    print(f"\nDetalle en {SALIDA}")
    return 0


def acierta(resultados: list[dict], caso: dict) -> bool | None:
    """None cuando el caso no tiene ancla: no hay nada que acertar."""
    doc = caso.get("documento_id")
    if not doc:
        return None
    return any(r.get("documento_id") == doc for r in resultados[:TOPE])


def informe_recuperacion(recuperado) -> None:
    anclados = [(c, r) for c, r, _ in recuperado if c.get("documento_id")]
    if not anclados:
        return
    ok = sum(1 for c, r in anclados if acierta(r, c))
    print(
        f"\nRECUPERACIÓN (sin costo): {ok}/{len(anclados)} = {ok / len(anclados) * 100:.1f}% "
        f"de los casos anclados traen el documento correcto entre los {TOPE} primeros"
    )
    por_tipo: dict[str, list[bool]] = defaultdict(list)
    for c, r in anclados:
        por_tipo[c["tipo"]].append(bool(acierta(r, c)))
    for t, v in sorted(por_tipo.items()):
        print(f"    {t:18} {sum(v):>3}/{len(v):<3} = {sum(v) / len(v) * 100:5.1f}%")


def informe(filas: list[dict], usd: float) -> None:
    print("\n" + "=" * 72)
    print("RESULTADO DEL PILOTO")
    print("=" * 72)
    anclados = [f for f in filas if f["documento_id"]]
    if anclados:
        ok = sum(1 for f in anclados if f["acierto_recuperacion"])
        print(f"Recuperación@{TOPE} : {ok}/{len(anclados)} = {ok / len(anclados) * 100:.1f}%")

    citas = sum(f["citas_totales"] for f in filas)
    lit = sum(f["citas_literales"] for f in filas)
    if citas:
        print(f"Citas literales   : {lit}/{citas} = {lit / citas * 100:.1f}% (el resto son citas INVENTADAS)")
    con_formato = sum(1 for f in filas if f["formato_ok"])
    print(f"Formato pedido    : {con_formato}/{len(filas)} = {con_formato / len(filas) * 100:.1f}%")

    abst = [f for f in filas if f["tipo"] == "no_cubierto"]
    if abst:
        ok = sum(1 for f in abst if f["se_abstuvo"])
        print(
            f"Abstención debida : {ok}/{len(abst)} = {ok / len(abst) * 100:.1f}% "
            f"(lo demás es inventar cobertura que no existe)"
        )

    trampas = [f for f in filas if f["tipo"] in ("trampa_derogada", "trampa_ambito")]
    if trampas:
        ok = sum(1 for f in trampas if f["advirtio_vigencia"] or f["se_abstuvo"])
        print(
            f"Trampas sorteadas : {ok}/{len(trampas)} = {ok / len(trampas) * 100:.1f}% "
            f"(norma derogada, inexequible o de otro ámbito)"
        )

    print("\nPor perfil de usuario:")
    por_perfil: dict[str, list[dict]] = defaultdict(list)
    for f in filas:
        por_perfil[f["perfil"]].append(f)
    for p, v in sorted(por_perfil.items(), key=lambda x: -len(x[1])):
        a = [x for x in v if x["documento_id"]]
        rec = f"{sum(1 for x in a if x['acierto_recuperacion']) / len(a) * 100:5.1f}%" if a else "    —"
        fm = sum(1 for x in v if x["formato_ok"]) / len(v) * 100
        print(f"  {p:24} n={len(v):<3} recuperación {rec}   formato {fm:5.1f}%")

    print(f"\nCosto real: {usd:.2f} USD (~{usd * 4100:,.0f} COP)")
    print(f"Tipos: {dict(Counter(f['tipo'] for f in filas))}")


if __name__ == "__main__":
    sys.exit(main())
