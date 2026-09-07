"""Cliente del índice remoto: misma interfaz que `IndiceBusqueda`, pero las
consultas viajan por HTTP a un servidor que sí tiene los ~11GB de índice.

Es la mitad cliente de la arquitectura "modelo local + índice en la nube":
el LLM sigue corriendo en la máquina del usuario (Ollama, privacidad, cero
costo por consulta) y solo la búsqueda —lo único que necesita el corpus
completo— sale a la red.

Intercambiable con el índice local sin tocar el resto del código:

    from index.buscar import IndiceBusqueda
    from index.cliente_remoto import IndiceRemoto

    indice = IndiceRemoto(url) if url else IndiceBusqueda()
    resultados = indice.buscar("prescripción de la acción disciplinaria", k=5)

Deliberadamente no importa nada de index.buscar: este módulo debe poder
usarse en un equipo donde ni torch ni chromadb estén instalados. Ese es
justamente el punto de mover el índice al servidor.
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request

TIEMPO_ESPERA_DEFECTO = 30.0  # s; una búsqueda típica tarda < 2s, pero un
# servidor recién despertado (plan barato con suspensión) puede tardar más
VAR_URL = "ALIADO_INDICE_URL"
VAR_TOKEN = "ALIADO_INDICE_TOKEN"

# Un servidor en plan barato se suspende por inactividad: el primer usuario
# tras una pausa se topa con un timeout o un 503 mientras el servicio carga
# los 11GB de indice. Fallar ahi seria culpar al usuario de la siesta del
# servidor, asi que se reintenta. Solo se reintenta lo que puede curarse
# esperando (timeout, conexion caida, 502/503/504): un 401 o un 404 se
# reintentan igual de mal, y multiplicarlos solo retrasa el mensaje util.
REINTENTOS_DEFECTO = 2  # intentos adicionales, no totales
ESPERA_ENTRE_INTENTOS = 2.0  # s; se duplica en cada reintento
CODIGOS_REINTENTABLES = frozenset({502, 503, 504})


class ErrorIndiceRemoto(RuntimeError):
    """Cualquier fallo al hablar con el servidor del índice. Trae siempre un
    mensaje en español pensado para mostrarse tal cual al usuario final."""


class IndiceRemoto:
    """Reemplazo transparente de `IndiceBusqueda` contra un servidor HTTP.

    url:     base del servidor, p. ej. "https://aliado-indice.onrender.com"
    token:   secreto compartido; si es None se toma de ALIADO_INDICE_TOKEN
    espera:  timeout en segundos para cada petición
    """

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        espera: float = TIEMPO_ESPERA_DEFECTO,
        reintentos: int = REINTENTOS_DEFECTO,
    ) -> None:
        url = (url or os.environ.get(VAR_URL, "")).strip().rstrip("/")
        if not url:
            raise ErrorIndiceRemoto(
                "No se indicó la dirección del índice remoto. Pásala al crear "
                f"IndiceRemoto(...) o define la variable de entorno {VAR_URL}."
            )
        self.url = url
        self.token = token if token is not None else os.environ.get(VAR_TOKEN, "").strip() or None
        self.espera = espera
        self.reintentos = max(0, int(reintentos))

    # -- interfaz pública -------------------------------------------------

    def buscar(self, consulta: str, k: int = 8, fuentes: list[str] | None = None) -> list[dict]:
        """Mismo contrato que IndiceBusqueda.buscar(): lista de dicts con
        'id', 'puntaje', 'texto' y los metadatos del fragmento.

        `fuentes` acota la busqueda a esas entidades; se manda solo cuando hay
        filtro, para que un servidor de una version anterior siga funcionando.
        """
        if not consulta or not consulta.strip():
            return []

        cuerpo = {"consulta": consulta.strip(), "n": k}
        if fuentes:
            cuerpo["fuentes"] = list(fuentes)
        datos = self._peticion("/buscar", cuerpo)
        resultados = datos.get("resultados")
        if not isinstance(resultados, list):
            raise ErrorIndiceRemoto(
                "El servidor del índice respondió con un formato inesperado (falta la lista 'resultados')."
            )
        return resultados

    def salud(self) -> dict:
        """Estado del servidor: fragmentos indexados y tiempo de carga.
        Útil para que la GUI diga 'índice remoto listo' antes de buscar."""
        return self._peticion("/salud", None)

    # -- transporte -------------------------------------------------------

    def _peticion(self, ruta: str, cuerpo: dict | None) -> dict:
        """Hace la petición reintentando solo los fallos que curan esperando."""
        espera_entre = ESPERA_ENTRE_INTENTOS
        for intento in range(self.reintentos + 1):
            try:
                return self._intento(ruta, cuerpo)
            except ErrorIndiceRemoto as e:
                if intento == self.reintentos or not getattr(e, "reintentable", False):
                    raise
                time.sleep(espera_entre)
                espera_entre *= 2
        raise AssertionError("inalcanzable")  # pragma: no cover

    def _intento(self, ruta: str, cuerpo: dict | None) -> dict:
        peticion = urllib.request.Request(self.url + ruta)
        peticion.add_header("Accept", "application/json")
        if self.token:
            peticion.add_header("Authorization", f"Bearer {self.token}")
        if cuerpo is not None:
            crudo = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
            peticion.add_header("Content-Type", "application/json; charset=utf-8")
            peticion.data = crudo  # urllib pasa a POST automáticamente

        try:
            with urllib.request.urlopen(peticion, timeout=self.espera) as respuesta:
                return self._leer_json(respuesta.read())
        except urllib.error.HTTPError as e:
            raise self._error(self._mensaje_http(e), e.code in CODIGOS_REINTENTABLES) from e
        except urllib.error.URLError as e:
            motivo = e.reason
            if isinstance(motivo, socket.timeout):
                raise self._error(self._mensaje_timeout(), True) from e
            raise self._error(
                f"No se pudo conectar con el servidor del índice ({self.url}): {motivo}. "
                "Revisa tu conexión y que la dirección sea correcta.",
                True,
            ) from e
        except TimeoutError as e:  # socket.timeout puro, sin envolver en URLError
            raise self._error(self._mensaje_timeout(), True) from e

    def _mensaje_timeout(self) -> str:
        return (
            f"El servidor del índice ({self.url}) no respondió en "
            f"{self.espera:g} segundos. Puede estar despertando o saturado; "
            "reintenta en un momento."
        )

    @staticmethod
    def _error(mensaje: str, reintentable: bool) -> ErrorIndiceRemoto:
        e = ErrorIndiceRemoto(mensaje)
        e.reintentable = reintentable
        return e

    @staticmethod
    def _leer_json(crudo: bytes) -> dict:
        try:
            datos = json.loads(crudo.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise IndiceRemoto._error(
                "El servidor del índice devolvió una respuesta que no es JSON válido.", False
            ) from e
        if not isinstance(datos, dict):
            raise ErrorIndiceRemoto("El servidor del índice devolvió un JSON con formato inesperado.")
        return datos

    def _mensaje_http(self, error: urllib.error.HTTPError) -> str:
        detalle = ""
        try:
            cuerpo = json.loads(error.read().decode("utf-8"))
            if isinstance(cuerpo, dict) and cuerpo.get("error"):
                detalle = f" Detalle: {cuerpo['error']}"
        except Exception:
            pass  # el cuerpo del error es opcional; nunca debe tapar el código HTTP

        if error.code == 401:
            return (
                "El servidor del índice rechazó la autenticación (401). Revisa el "
                f"token compartido (variable {VAR_TOKEN})." + detalle
            )
        if error.code == 404:
            return (
                f"La dirección del índice ({self.url}) no expone este servicio (404). "
                "Verifica la URL." + detalle
            )
        if error.code == 503:
            return "El servidor del índice todavía no terminó de cargar (503). Reintenta." + detalle
        if 500 <= error.code < 600:
            return f"El servidor del índice falló ({error.code}).{detalle}"
        return f"El servidor del índice rechazó la petición ({error.code}).{detalle}"
