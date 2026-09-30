"""Servidor web local de Aliado Libre — solo stdlib, sin frameworks (mismo
patrón que NativoWeb en otros proyectos de la suite). Sirve la página en
gui/static/index.html y expone /api/buscar como único endpoint.

El índice (modelo de embeddings + Chroma + BM25) se carga perezosamente en
el primer request de búsqueda, no al arrancar el servidor — así abrir la
página no compite por CPU/memoria hasta que alguien busca de verdad."""

from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ESTA_CONGELADO = bool(getattr(sys, "frozen", False))


def _raiz_recursos() -> Path:
    """Raíz desde la que colgar recursos (gui/static/...).

    En el .exe de PyInstaller el código vive dentro del archivo comprimido y
    ``__file__`` no apunta a una carpeta real: los datos se extraen a
    ``sys._MEIPASS``. En desarrollo la raíz es la del repositorio."""
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return Path(base)
    return Path(__file__).resolve().parent.parent


RAIZ = _raiz_recursos()
if not ESTA_CONGELADO:
    sys.path.insert(0, str(RAIZ))

from confianza_tls import confiar_en_almacen_del_sistema  # noqa: E402
from drenar_cuerpo import descartar_cuerpo  # noqa: E402

RAIZ_ESTATICA = RAIZ / "gui" / "static"
PUERTO = 8765

_indice = None
_indice_lock = threading.Lock()


def _crear_indice():
    """Elige índice remoto o local.

    El .exe distribuible NO lleva el corpus, ni Chroma, ni el modelo de
    embeddings: consulta el índice por HTTP (``index.cliente_remoto``), así
    que congelado siempre va por ahí.

    En desarrollo manda ``ALIADO_INDICE_URL``: si está definida se usa el
    servidor remoto, y si no, el índice local del repositorio. Decidirlo por
    la URL y no por si el import funciona es lo único correcto: en el repo el
    import SIEMPRE funciona, así que ese criterio dejaba el índice local
    inalcanzable y rompía el arranque de toda la vida (`python gui/server.py`)
    contra un servidor que puede no estar desplegado.
    """
    hay_url = bool(os.environ.get("ALIADO_INDICE_URL", "").strip())

    if ESTA_CONGELADO or hay_url:
        try:
            from index.cliente_remoto import IndiceRemoto
        except ImportError:
            raise RuntimeError(
                "Esta versión empaquetada necesita el cliente de índice remoto "
                "(index/cliente_remoto.py) y se compiló sin él."
            ) from None
        return IndiceRemoto()

    from index.buscar import IndiceBusqueda

    return IndiceBusqueda()


def _costo_a_dict(costo) -> dict:
    return {
        "usd": round(costo.usd, 6),
        "pesos": costo.pesos,
        "tokens_entrada": costo.tokens_entrada,
        "tokens_salida": costo.tokens_salida,
        "modelo": costo.modelo,
        "estimado": costo.estimado,
        "texto": costo.texto(),
        "aviso": costo.aviso,
    }


def _obtener_indice():
    global _indice
    with _indice_lock:
        if _indice is None:
            _indice = _crear_indice()
    return _indice


class Handler(BaseHTTPRequestHandler):
    # Se pone en True en cuanto el cuerpo se lee o se drena, para que dos
    # caminos de error seguidos no intenten leerlo dos veces.
    cuerpo_consumido = False

    def log_message(self, formato, *args):  # silencia el log por defecto, ruidoso
        pass

    def do_GET(self):
        ruta = urlparse(self.path)

        if ruta.path == "/api/buscar":
            self._responder_busqueda(ruta)
            return

        if ruta.path == "/api/estado":
            # Se informa si el modelo local existe DE VERDAD. La casilla
            # "redactar con el modelo propio" se ofrecia siempre, y cuando el
            # .gguf no estaba en su sitio el usuario pulsaba, esperaba, y
            # recibia un error tecnico sobre un archivo que le faltaba. Ofrecer
            # lo que no se tiene es la version pequena de inventar cobertura.
            from gui import publico
            from index.responder import ruta_modelo

            self._responder_json(
                {
                    "cargado": _indice is not None,
                    # En público no se ofrece el modelo local: redacta la nube.
                    "modelo_local": ruta_modelo().is_file() and not publico.activo(),
                    "publico": publico.activo(),
                    "nombre": publico.nombre_producto(),
                    "redacciones_diarias": publico.cuota_redaccion().tope_ip if publico.activo() else None,
                }
            )
            return

        if ruta.path == "/api/fuentes":
            # Se sirve sin cargar el índice: sale del índice léxico, que es
            # barato de leer. Así la lista de entidades aparece de inmediato
            # aunque nadie haya buscado todavía.
            from index.fuentes import resumen

            self._responder_json(resumen())
            return

        self._servir_estatico(ruta.path)

    def do_POST(self):  # noqa: N802 (nombre impuesto por BaseHTTPRequestHandler)
        ruta = urlparse(self.path)
        if ruta.path != "/api/responder":
            # El cuerpo se lee y se tira ANTES de contestar. Sin esto el cliente
            # sigue escribiendo en un socket ya cerrado y en Windows recibe una
            # conexión abortada en vez del 404: era el fallo intermitente de
            # tests/test_ia_externa_endpoint.py. Ver drenar_cuerpo.py.
            descartar_cuerpo(self)
            self.send_error(404)
            return
        self._responder_con_ia_externa()

    def _leer_json(self, maximo: int = 256 * 1024) -> dict | None:
        """Devuelve el dict del cuerpo, o None si no sirve.

        En todos los caminos que devuelven None el cuerpo queda drenado: quien
        llama va a contestar un 400, y contestar un error sin leer lo que el
        cliente todavía está escribiendo se convierte en una conexión abortada.
        """
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            descartar_cuerpo(self)
            return None
        if largo <= 0:
            return None
        if largo > maximo:
            descartar_cuerpo(self)
            return None
        try:
            datos = json.loads(self.rfile.read(largo).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            # el read ya consumió el cuerpo; marcarlo evita un segundo intento
            self.cuerpo_consumido = True
            return None
        self.cuerpo_consumido = True
        return datos if isinstance(datos, dict) else None

    def _responder_con_ia_externa(self) -> None:
        """Redacta con el proveedor y la clave que puso el usuario.

        La clave llega en el cuerpo de esta petición, se usa para una sola
        llamada y se descarta. No se guarda, no se registra, y `proveedores`
        la borra de cualquier mensaje de error antes de devolverlo.
        """
        from index import costos
        from index.proveedores import MODELOS_POR_DEFECTO, ErrorProveedor, generar
        from index.responder import PROMPT_SISTEMA, _formatear_fragmentos

        datos = self._leer_json()
        if datos is None:
            self._responder_json({"error": "Cuerpo inválido."}, status=400)
            return

        consulta = (datos.get("consulta") or "").strip()
        fragmentos = datos.get("fragmentos")
        proveedor = (datos.get("proveedor") or "").strip().lower()
        if not consulta or not isinstance(fragmentos, list) or not proveedor:
            self._responder_json({"error": "Faltan 'consulta', 'fragmentos' o 'proveedor'."}, status=400)
            return

        modelo = (datos.get("modelo") or "").strip() or MODELOS_POR_DEFECTO.get(proveedor, "")
        # Los proveedores externos reciben el sistema por su propio parametro,
        # asi que aqui el prompt lleva solo contexto y pregunta: usar
        # construir_prompt() duplicaria PROMPT_SISTEMA dentro del mensaje.
        contexto = _formatear_fragmentos(fragmentos[:8])
        prompt = f"Fragmentos disponibles:\n\n{contexto}\n\nPregunta: {consulta}\n\nRespuesta:"

        # Solo estimar: no se llama al proveedor ni se necesita la clave.
        if datos.get("solo_estimar"):
            self._responder_json({"estimado": _costo_a_dict(costos.estimar(prompt, modelo))})
            return

        try:
            r = generar(prompt, PROMPT_SISTEMA, proveedor, clave=datos.get("clave"), modelo=modelo)
        except ErrorProveedor as e:
            self._responder_json({"error": str(e)}, status=502)
            return

        from index.verificar_anclaje import marcar, verificar
        from index.vigencia import garantizar_advertencia, vigencia_de

        # Los fragmentos vienen del navegador: la vigencia se recalcula aquí,
        # no se cree la que traigan.
        usados = [f for f in fragmentos[:8] if isinstance(f, dict)]
        for f in usados:
            f["vigencia"] = vigencia_de(f)
        informe = verificar(r.texto, usados)
        texto = garantizar_advertencia(r.texto, usados)

        from index.enrutador import decidir
        from index.respaldo import respaldo_suficiente

        # Misma regla que la búsqueda: con coincidencia débil solo se muestra una
        # respuesta cuyas citas estén TODAS, literalmente, en las fuentes. La
        # persona pagó la llamada, así que se le dice cuánto y por qué se retiene.
        if decidir(usados, hay_clave_externa=True).motor == "condicional":
            aceptada, motivo = respaldo_suficiente(r.texto, usados)
            if not aceptada:
                self._responder_json(
                    {
                        "respuesta": None,
                        "retenida": motivo + " Revisa los fragmentos como pista.",
                        "proveedor": r.proveedor,
                        "modelo": r.modelo,
                        "costo": _costo_a_dict(costos.liquidar(r.usage, r.modelo)),
                    }
                )
                return
        self._responder_json(
            {
                "respuesta": texto if informe.anclada else marcar(texto, informe),
                "anclada": informe.anclada,
                "aviso_anclaje": "" if informe.anclada else informe.resumen(),
                "proveedor": r.proveedor,
                "modelo": r.modelo,
                "costo": _costo_a_dict(costos.liquidar(r.usage, r.modelo)),
            }
        )

    def _responder_busqueda(self, ruta):
        params = parse_qs(ruta.query)
        consulta = (params.get("q") or [""])[0].strip()
        if not consulta:
            self._responder_json({"error": "Consulta vacía"}, status=400)
            return

        try:
            k = int((params.get("k") or ["8"])[0])
        except ValueError:
            k = 8

        quiere_respuesta = (params.get("conversacional") or ["0"])[0] == "1"

        # Modo público (gui/publico.py): gratis con tope diario por huella de IP.
        from gui import publico

        aviso_aporte_publico = None
        if publico.activo():
            from servidor_indice.cuotas import mensaje_aporte, mensaje_bloqueo

            v = publico.cuota_busqueda().consumir(publico.ip_cliente(self))
            if not v.permitido:
                self._responder_json({"error": mensaje_bloqueo(v), "limite": True}, status=429)
                return
            if v.sugerir_aporte:
                aviso_aporte_publico = mensaje_aporte(v)

        # "fuentes" llega repetido (fuentes=sic&fuentes=dian) o separado por
        # comas; se aceptan las dos formas para que la URL sea legible.
        from index.fuentes import normalizar

        crudas: list[str] = []
        for valor in params.get("fuentes") or []:
            crudas.extend(p.strip() for p in valor.split(",") if p.strip())
        fuentes = normalizar(crudas)

        try:
            indice = _obtener_indice()
            resultados = indice.buscar(consulta, k=k, fuentes=fuentes)
        except Exception as e:
            self._responder_json({"error": str(e)}, status=500)
            return

        # El índice sabe cuándo no tiene la respuesta, y hasta hoy no se lo
        # decía a nadie. `index/enrutador.py` calcula la abstención con un
        # umbral calibrado y la GUI no lo consultaba: ante «puedo tener mi
        # herencia antes de que mueran mis padres» el enrutador dictaminaba
        # "ningún documento se acerca lo suficiente" y la pantalla mostraba,
        # con toda seriedad, un decreto de 1938 sobre la Caja de Auxilios de la
        # Policía Nacional. Es justo lo que la regla 1 del proyecto prohíbe:
        # los huecos del índice se dicen, no se disimulan.
        from index.enrutador import decidir

        decision = decidir(resultados, hay_clave_externa=True)
        # Solo el índice remoto tiene cuota; en "todo local" no existe este aviso.
        aviso_aporte = aviso_aporte_publico or getattr(indice, "ultimo_aviso_aporte", None)
        salida = {
            "resultados": resultados,
            "fuentes_aplicadas": fuentes or [],
            "hay_respaldo": decision.responde,
            "aviso_cobertura": None if decision.responde else decision.motivo,
            "aviso_aporte": aviso_aporte,
            # "claro" | "condicional" (coincidencia débil: se redacta, pero solo se
            # muestra si pasa index.respaldo) | "ninguno"
            "respaldo": "claro"
            if decision.responde
            else ("condicional" if decision.puede_redactar else "ninguno"),
        }
        if quiere_respuesta and not decision.puede_redactar:
            # Redactar sobre fragmentos que no responden es la forma más cara de
            # inventar cobertura: sale una respuesta con aspecto de buena.
            salida["respuesta"] = None
            self._responder_json(salida)
            return
        if quiere_respuesta:
            from index.responder import responder

            # menos fragmentos que los mostrados: el prompt crece con cada
            # uno y en CPU la respuesta se vuelve notablemente más lenta
            MAX_FRAGMENTOS_CONVERSACIONAL = 4
            usados = resultados[:MAX_FRAGMENTOS_CONVERSACIONAL]
            try:
                if publico.activo():
                    texto = self._redactar_publico(consulta, usados)
                    if texto is None:
                        salida["respuesta"] = None
                        salida["aviso_respuesta"] = self._aviso_redaccion
                        self._responder_json(salida)
                        return
                else:
                    texto = responder(consulta, usados)
                # Comprobación determinista antes de mostrar nada: cada número de
                # norma, artículo, plazo o cifra de la respuesta tiene que estar
                # en los fragmentos. Medido sobre 150 respuestas reales, marca 21
                # y las 21 eran malas — ningún falso positivo. No sustituye leer
                # la cita, pero convierte un dato inventado en algo visible en
                # vez de en prosa convincente.
                from index.verificar_anclaje import marcar, verificar

                informe = verificar(texto, usados)
                if decision.motor == "condicional":
                    from index.respaldo import respaldo_suficiente

                    aceptada, motivo = respaldo_suficiente(texto, usados)
                    if not aceptada or not informe.anclada:
                        # Coincidencia débil y respuesta sin respaldo literal: no
                        # se muestra. Los fragmentos siguen como pista.
                        salida["respuesta"] = None
                        salida["aviso_respuesta"] = (
                            "No muestro una respuesta redactada: "
                            + (motivo or informe.resumen())
                            + " Revisa los fragmentos de abajo como pista."
                        )
                        self._responder_json(salida)
                        return
                    salida["hay_respaldo"] = True
                    salida["respaldo_debil"] = True
                salida["respuesta"] = texto if informe.anclada else marcar(texto, informe)
                salida["anclada"] = informe.anclada
                if not informe.anclada:
                    salida["aviso_anclaje"] = informe.resumen()
            except RuntimeError as e:
                # modelo GGUF ausente, no cargable o fallo de inferencia:
                # degradar a buscador puro, no tirar toda la respuesta.
                # El mensaje de `responder` ya explica en español qué falta.
                salida["respuesta"] = None
                salida["aviso_respuesta"] = str(e)

        self._responder_json(salida)

    def _redactar_publico(self, consulta: str, usados: list[dict]) -> str | None:
        """Redacta con la clave del servidor si quedan redacciones gratis hoy y
        presupuesto este mes. None = no se redacta (motivo en _aviso_redaccion);
        la búsqueda con citas sigue funcionando igual."""
        from gui import publico
        from index.vigencia import garantizar_advertencia

        mes = publico.mes_actual()
        if not publico.presupuesto().queda(mes):
            self._aviso_redaccion = (
                "Las respuestas redactadas por IA están en pausa este mes (se agotó el presupuesto "
                "del servicio gratuito). Las normas y sus citas de abajo siguen disponibles."
            )
            return None
        v = publico.cuota_redaccion().consumir(publico.ip_cliente(self))
        if not v.permitido:
            self._aviso_redaccion = (
                f"Ya usaste tus {v.tope} respuestas redactadas gratis de hoy. Puedes seguir buscando: "
                "las normas y sus citas de abajo no tienen ese límite."
            )
            return None
        texto, usd = publico.redactar(consulta, usados)
        publico.presupuesto().registrar(mes, usd)
        return garantizar_advertencia(texto, usados)

    def _servir_estatico(self, ruta_pedida: str) -> None:
        nombre = "index.html" if ruta_pedida in ("/", "") else ruta_pedida.lstrip("/")
        archivo = (RAIZ_ESTATICA / nombre).resolve()

        # nunca servir nada fuera de gui/static/
        if RAIZ_ESTATICA not in archivo.parents and archivo != RAIZ_ESTATICA:
            self.send_error(404)
            return
        if not archivo.is_file():
            self.send_error(404)
            return

        tipo = "text/html" if archivo.suffix == ".html" else "application/octet-stream"
        cuerpo = archivo.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _responder_json(self, datos: dict, status: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)


def main() -> None:
    # Antes de abrir nada: con un antivirus que inspecciona TLS (Norton, Avast,
    # Kaspersky…), las llamadas a la IA de nube y al índice remoto fallarían con
    # CERTIFICATE_VERIFY_FAILED. Ver confianza_tls.py.
    confiar_en_almacen_del_sistema()
    from gui import publico

    puerto = int(os.environ.get("ALIADO_PUERTO", PUERTO))
    # Siempre 127.0.0.1, también en público: el túnel (Cloudflare) se conecta
    # desde dentro de la máquina, así que no hace falta abrir nada a la red.
    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), Handler)
    url = f"http://127.0.0.1:{puerto}"
    if publico.activo():
        print(f"{publico.nombre_producto()} en MODO PÚBLICO en {url} — exponer con el túnel.")
    else:
        print(f"Aliado Libre corriendo en {url} (Ctrl+C para detener)")
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
