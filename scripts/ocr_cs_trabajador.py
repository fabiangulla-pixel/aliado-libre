"""Paso 2 del OCR de la Corte Suprema: baja cada sentencia pendiente y la pasa
por PaddleOCR en la GPU. Corre en el venv de Paddle, NO en el del proyecto:

    C:\\dev\\venv-paddle\\Scripts\\python.exe scripts\\ocr_cs_trabajador.py --parte 0 --partes 1

Lo lanza scripts/ocr_cs_lanzar.ps1 (tarea programada "AliadoLibre-OCR", la
registra scripts/ocr_cs_tarea.ps1), que lo vuelve a arrancar al iniciar sesión
o si se cae. Con --partes N, N procesos comparten la GPU repartiéndose las
sentencias por hash del id. Pensado para cortarse en cualquier momento sin
perder más que la sentencia en curso:

- Cada sentencia terminada se agrega como una línea a resultados_p<parte>.jsonl
  con flush + fsync. Al arrancar se descarta una última línea a medias (apagón).
- Las que fallan de forma definitiva (no existe ni en .pdf ni en .docx) van a
  fallidos_p<parte>.jsonl y no se reintentan. Un corte de red NO es fallo definitivo:
  espera y reintenta.
- Sale solo (y la tarea lo relanza luego) si existe data/ocr_corte_suprema/PAUSA
  o si el equipo pasa a batería.
- Mientras trabaja, le pide a Windows que no suspenda el equipo.

Medido el 15-nov-2026 sobre PDF digitales de la Corte (la capa de texto como
referencia exacta): recall de palabras 99,0% a 200 dpi con PP-OCRv5 mobile_det,
0,82 s/página con la GPU compartida. Las páginas que ya traen capa de texto no
pasan por OCR."""

from __future__ import annotations

import argparse
import ctypes
import glob
import html
import io
import json
import os
import queue
import re
import site
import sys
import threading
import time
import warnings
import zipfile
import zlib
from pathlib import Path

warnings.filterwarnings("ignore")
# Las DLL de CUDA vienen en site-packages/nvidia/** y Paddle no las encuentra solo.
for _d in sorted(
    {
        os.path.dirname(p)
        for sp in site.getsitepackages()
        for p in glob.glob(os.path.join(sp, "nvidia", "**", "*.dll"), recursive=True)
    }
):
    os.add_dll_directory(_d)
    os.environ["PATH"] = _d + os.pathsep + os.environ["PATH"]
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

import requests  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "data" / "ocr_corte_suprema"
PENDIENTES = CARPETA / "pendientes.jsonl"
RESULTADOS = CARPETA / "resultados.jsonl"
FALLIDOS = CARPETA / "fallidos.jsonl"
LISTADOS = CARPETA / "_listados.json"
TERMINADO = CARPETA / "_terminado"
PAUSA = CARPETA / "PAUSA"

DOWNLOAD_URL = "https://consultaprovidenciasbk.cortesuprema.gov.co/downloadFile"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Origin": "https://consultaprovidencias.cortesuprema.gov.co",
    "Referer": "https://consultaprovidencias.cortesuprema.gov.co/",
}
DPI = 200
MAX_PAGINAS = 200
TEXTO_NATIVO_MINIMO = 200  # caracteres no blancos para confiar en la capa de texto
CONFIANZA_MINIMA = 0.5  # por línea; filtra restos de la marca de agua
SALAS_POR_ANIO = 2 * (2026 - 1990 + 1)  # pares (sala, año) que lista el paso 1


class FalloDefinitivo(Exception):
    pass


# ---------------------------------------------------------------- persistencia


def reparar_cola(ruta: Path) -> None:
    """Si un apagón dejó la última línea a medias, se corta hasta el último \\n."""
    if not ruta.exists() or ruta.stat().st_size == 0:
        return
    with ruta.open("rb+") as f:
        f.seek(-1, os.SEEK_END)
        if f.read(1) == b"\n":
            return
        datos = ruta.read_bytes()
        f.seek(0)
        f.truncate(datos.rfind(b"\n") + 1)


def leer_ids(ruta: Path) -> set[str]:
    ids = set()
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            try:
                ids.add(json.loads(linea)["id"])
            except (json.JSONDecodeError, KeyError):
                pass
    return ids


def anexar(ruta: Path, fila: dict) -> None:
    with ruta.open("a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def ids_hechos() -> set[str]:
    """Todas las partes, de esta corrida o de corridas con otro número de partes."""
    hechos: set[str] = set()
    for ruta in [*CARPETA.glob("resultados*.jsonl"), *CARPETA.glob("fallidos*.jsonl")]:
        hechos |= leer_ids(ruta)
    return hechos


def parte_de(id_: str, partes: int) -> int:
    return zlib.crc32(id_.encode("utf-8")) % partes


def pendientes(parte: int = 0, partes: int = 1) -> list[dict]:
    hechos = ids_hechos()
    filas = [json.loads(x) for x in PENDIENTES.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [f for f in filas if f["id"] not in hechos and parte_de(f["id"], partes) == parte]


# ---------------------------------------------------------------- entorno


def mantener_despierto(activo: bool) -> None:
    es_continuous, es_system_required = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(es_continuous | (es_system_required if activo else 0))


def en_bateria() -> bool:
    class Estado(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_byte),
            ("BatteryFlag", ctypes.c_byte),
            ("BatteryLifePercent", ctypes.c_byte),
            ("SystemStatusFlag", ctypes.c_byte),
            ("BatteryLifeTime", ctypes.c_ulong),
            ("BatteryFullLifeTime", ctypes.c_ulong),
        ]

    e = Estado()
    return bool(ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(e))) and e.ACLineStatus == 0


def debe_parar() -> str | None:
    if PAUSA.exists():
        return "existe el archivo PAUSA"
    if en_bateria():
        return "el equipo está en batería"
    return None


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


# ---------------------------------------------------------------- descarga y páginas


def descargar(sesion: requests.Session, ruta: str) -> bytes:
    espera = 30
    while True:
        try:
            r = sesion.post(DOWNLOAD_URL, json={"path": ruta}, verify=False, timeout=120)
            if r.status_code == 404 or r.content[:9] == b"Not Found":
                raise FalloDefinitivo("el servidor no tiene el archivo")
            r.raise_for_status()
            if not r.content:
                raise FalloDefinitivo("archivo vacío")
            return r.content
        except requests.exceptions.RequestException as e:
            # Red caída o 5xx del proxy: no es culpa del archivo. Se espera y se reintenta.
            log(f"  red: {type(e).__name__}; reintento en {espera} s")
            time.sleep(espera)
            espera = min(espera * 2, 600)
            if debe_parar():
                raise


def bajar_alguna(sesion: requests.Session, ruta: str) -> tuple[str, bytes]:
    """El listado ofrece el .docx cuando existen ambos, pero el servidor a
    menudo no lo tiene (todo Laboral 2024, p. ej.) y sí el .pdf: se prueban las
    dos extensiones, primero la listada. Verificado 15-nov-2026."""
    base, _, ext = ruta.rpartition(".")
    ext = ext.lower()
    # Un .doc (Word 97) no se lee sin dependencias nuevas: se buscan sus hermanos.
    for candidata in dict.fromkeys(e for e in (ext, "pdf", "docx") if e in ("pdf", "docx")):
        try:
            return candidata, descargar(sesion, f"{base}.{candidata}")
        except FalloDefinitivo:
            continue
    if ext not in ("pdf", "docx"):
        raise FalloDefinitivo(f"formato .{ext} no soportado y sin .pdf/.docx")
    raise FalloDefinitivo("el servidor no tiene el archivo (ni .pdf ni .docx)")


def texto_docx(contenido: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    parrafos = []
    for p in re.split(r"</w:p>", xml):
        trozos = re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", p)
        if trozos:
            parrafos.append(html.unescape("".join(trozos)).strip())
    return "\n".join(x for x in parrafos if x)


def productor(trabajo: list[dict], cola: queue.Queue, parar: threading.Event) -> None:
    """Hilo único (pdfium no es seguro entre hilos): baja, separa páginas con
    capa de texto de las que necesitan OCR y las encola en orden."""
    import pypdfium2 as pdfium  # solo en el venv de Paddle; así los tests importan el módulo

    sesion = requests.Session()
    sesion.headers.update(HEADERS)
    for fila in trabajo:
        if parar.is_set():
            break
        try:
            ext, contenido = bajar_alguna(sesion, fila["ruta"])
            if ext == "docx":
                cola.put((fila, "texto", texto_docx(contenido)))
                continue
            try:
                doc = pdfium.PdfDocument(contenido)
            except pdfium.PdfiumError as e:
                raise FalloDefinitivo(f"PDF ilegible: {e}") from e
            n = len(doc)
            paginas = []
            for i in range(min(n, MAX_PAGINAS)):
                pag = doc[i]
                nativo = pag.get_textpage().get_text_range()
                if len(re.sub(r"\s", "", nativo)) >= TEXTO_NATIVO_MINIMO:
                    paginas.append(("texto", nativo))
                else:
                    paginas.append(("imagen", pag.render(scale=DPI / 72).to_numpy()))
                pag.close()
            doc.close()
            cola.put((fila, "paginas", {"paginas": paginas, "total": n}))
        except FalloDefinitivo as e:
            cola.put((fila, "fallo", str(e)))
        except Exception as e:  # noqa: BLE001 - un archivo raro no debe tumbar la corrida
            if parar.is_set() or debe_parar():
                break
            cola.put((fila, "fallo", f"{type(e).__name__}: {e}"))
    cola.put(None)


# ---------------------------------------------------------------- OCR


def cargar_motor():
    import paddleocr

    return paddleocr.PaddleOCR(
        lang="es",
        text_detection_model_name="PP-OCRv5_mobile_det",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_recognition_batch_size=16,
    )


def ocr_pagina(motor, imagen) -> tuple[str, list[float]]:
    res = motor.predict(imagen)[0].json["res"]
    lineas, confs = [], []
    for t, s in zip(res.get("rec_texts", []), res.get("rec_scores", []), strict=False):
        if s >= CONFIANZA_MINIMA and t.strip():
            lineas.append(t.strip())
            confs.append(float(s))
    return "\n".join(lineas), confs


def main() -> int:
    global RESULTADOS, FALLIDOS
    ap = argparse.ArgumentParser()
    ap.add_argument("--parte", type=int, default=0)
    ap.add_argument("--partes", type=int, default=1)
    args = ap.parse_args()
    CARPETA.mkdir(parents=True, exist_ok=True)
    # Un archivo por parte: dos procesos nunca anexan al mismo (líneas de 50 KB no son atómicas).
    RESULTADOS = CARPETA / f"resultados_p{args.parte}.jsonl"
    FALLIDOS = CARPETA / f"fallidos_p{args.parte}.jsonl"
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    if (motivo := debe_parar()) is not None:
        log(f"No arranco: {motivo}")
        return 0
    # Solo los propios: otra parte puede estar escribiendo los suyos ahora mismo.
    # Una línea a medias ajena la ignora leer_ids y la corta su dueña al arrancar.
    reparar_cola(RESULTADOS)
    reparar_cola(FALLIDOS)
    trabajo = pendientes(args.parte, args.partes)
    listados = json.loads(LISTADOS.read_text(encoding="utf-8")) if LISTADOS.exists() else []
    listado_completo = len(listados) >= SALAS_POR_ANIO
    hechos_previos = len(ids_hechos())
    log(
        f"Parte {args.parte}/{args.partes}: {len(trabajo)} pendientes; "
        f"{hechos_previos} ya resueltas en total; listado completo: {listado_completo}"
    )
    if not trabajo:
        if listado_completo and not pendientes():  # ninguna parte tiene nada
            TERMINADO.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="ascii")
            log("Nada pendiente en ninguna parte: marcado como terminado.")
        return 0

    mantener_despierto(True)
    motor = cargar_motor()
    log("Motor cargado en GPU.")
    cola: queue.Queue = queue.Queue(maxsize=3)  # ~3 sentencias por delante; acota RAM
    parar = threading.Event()
    hilo = threading.Thread(target=productor, args=(trabajo, cola, parar), daemon=True)
    hilo.start()
    t0, docs, pags_ocr = time.time(), 0, 0
    tope = int(os.environ.get("OCR_MAX_DOCS") or 0)  # solo para pruebas; 0 = sin tope
    try:
        while (item := cola.get()) is not None:
            fila, tipo, carga = item
            if tipo == "fallo":
                anexar(FALLIDOS, {"id": fila["id"], "ruta": fila["ruta"], "motivo": carga})
                continue
            if tipo == "texto":
                textos, confs, n_ocr, total = [carga], [], 0, None
            else:
                textos, confs, n_ocr = [], [], 0
                total = carga["total"]
                for clase, contenido in carga["paginas"]:
                    if clase == "texto":
                        textos.append(contenido)
                    else:
                        t, c = ocr_pagina(motor, contenido)
                        textos.append(t)
                        confs.extend(c)
                        n_ocr += 1
            texto = "\n\n".join(t.strip() for t in textos if t.strip())
            if len(texto) < 100:
                anexar(FALLIDOS, {"id": fila["id"], "ruta": fila["ruta"], "motivo": "sin texto legible"})
                continue
            anexar(
                RESULTADOS,
                {
                    **fila,
                    "texto": texto,
                    "paginas": total,
                    "paginas_ocr": n_ocr,
                    "truncado": bool(total and total > MAX_PAGINAS),
                    "confianza": round(sum(confs) / len(confs), 4) if confs else None,
                },
            )
            docs += 1
            pags_ocr += n_ocr
            if docs % 20 == 0:
                dt = time.time() - t0
                resto = len(trabajo) - docs
                log(
                    f"{hechos_previos + docs} hechas | {docs / dt * 3600:.0f} sent/h, "
                    f"{pags_ocr / dt:.2f} pág OCR/s | quedan {resto} (~{resto / (docs / dt) / 3600:.1f} h)"
                )
            if (motivo := debe_parar()) is not None:
                log(f"Pauso: {motivo}. Retomo desde aquí la próxima vez.")
                break
            if tope and docs >= tope:
                log("Tope OCR_MAX_DOCS alcanzado (prueba).")
                break
    finally:
        parar.set()
        mantener_despierto(False)
    log(f"Salgo: {docs} sentencias en esta corrida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
