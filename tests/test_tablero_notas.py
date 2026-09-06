"""El tablero de notas no sale del navegador.

La promesa al usuario es que puede ir apartando sentencias y fuentes durante su
sesión, exportarlas a su equipo, y que la aplicación no guarde rastro de nada.
Eso obliga a dos cosas verificables desde aquí:

1. El servidor no expone ningún endpoint que reciba notas.
2. La lógica del tablero no hace ninguna petición de red.

Es una prueba de contrato sobre el archivo, no de comportamiento del navegador;
lo segundo necesitaría un navegador real. Vale la pena igual: protege contra el
cambio más probable —"guardemos el tablero en el servidor para que no se
pierda"— que rompería la promesa sin que nadie lo note.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HTML = (RAIZ / "gui" / "static" / "index.html").read_text(encoding="utf-8")
SERVIDOR_GUI = (RAIZ / "gui" / "server.py").read_text(encoding="utf-8")


def _sin_comentarios(js: str) -> str:
    """Quita comentarios: explicar por qué NO se usa algo no es usarlo."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", js, flags=re.MULTILINE)


def _bloque_tablero() -> str:
    """Solo el código del tablero, sin el comentario que lo introduce.

    El comentario explica por qué NO se usa localStorage ni fetch; incluirlo
    haría que estas pruebas se dispararan con su propia justificación.
    """
    inicio = HTML.index("const CLAVE_TABLERO")
    # El selector de fuentes viene despues en el mismo <script> y SI hace fetch:
    # acotar el bloque evita que estas pruebas juzguen codigo ajeno.
    fin = HTML.index("Selector de fuentes", inicio)
    return HTML[inicio:fin]


def test_el_tablero_existe_con_sus_controles():
    for elemento in ("tableroCuerpo", "exportarMd", "exportarTxt", "vaciarTablero"):
        assert f'id="{elemento}"' in HTML, f"falta el elemento {elemento}"


def test_la_logica_del_tablero_no_hace_peticiones():
    bloque = _bloque_tablero()
    for prohibido in ("fetch(", "XMLHttpRequest", "navigator.sendBeacon", "WebSocket"):
        # el comentario del módulo menciona 'fetch' para explicar la regla
        apariciones = [
            linea
            for linea in bloque.splitlines()
            if prohibido in linea and not linea.strip().startswith(("//", "*", "/*"))
        ]
        assert not apariciones, f"el tablero usa {prohibido}: {apariciones}"


def test_usa_sessionstorage_y_no_localstorage():
    """localStorage sobreviviría a cerrar la pestaña, y eso deja rastro en un
    computador compartido."""
    codigo = _sin_comentarios(_bloque_tablero())
    assert "sessionStorage" in codigo
    assert "localStorage" not in codigo, "localStorage sobrevive a cerrar la pestaña"


def test_el_servidor_no_recibe_notas():
    """Ningún endpoint del servidor acepta el contenido del tablero."""
    rutas = set(re.findall(r'ruta\.path == "([^"]+)"', SERVIDOR_GUI))
    permitidos = {"/api/buscar", "/api/estado", "/api/fuentes"}
    assert rutas <= permitidos, f"endpoints inesperados: {rutas - permitidos}"
    for sospechoso in ("notas", "tablero", "favoritos"):
        assert sospechoso not in SERVIDOR_GUI.lower(), (
            f"el servidor menciona {sospechoso!r}: ¿está recibiendo el tablero?"
        )


def test_el_acceso_al_almacenamiento_esta_protegido():
    """En modo privado sessionStorage puede lanzar: no debe tumbar la página."""
    bloque = _bloque_tablero()
    for funcion in ("function leerNotas", "function guardarNotas"):
        cuerpo = bloque[bloque.index(funcion) :]
        cuerpo = cuerpo[: cuerpo.index("\n}")]
        assert "try {" in cuerpo, f"{funcion} accede al almacenamiento sin try/catch"


def test_se_le_avisa_al_usuario_que_el_tablero_es_efimero():
    assert "desaparece al cerrar" in HTML
    assert "ni se guarda en el servidor" in HTML


def test_la_exportacion_incluye_lo_necesario_para_citar():
    bloque = _bloque_tablero()
    for campo in ("Identificador", "Fuente", "Enlace"):
        assert campo in bloque, f"la exportación no incluye {campo}"


# --- bugs encontrados usando la app de verdad -------------------------------


def test_el_tablero_oculto_se_oculta_de_verdad():
    """`display: flex` gana sobre el display:none que trae [hidden].

    Sin esta regla el tablero aparecía con "Mi tablero (0)" aunque no hubiera
    nada guardado. Visto en uso real desde un celular.
    """
    assert "#tablero[hidden]" in HTML
    assert "#tablero[hidden] { display: none; }" in HTML


def test_las_respuestas_se_leen_comprobando_que_sean_json():
    """Un proxy o un tiempo de espera agotado devuelven HTML, no JSON.

    Sin comprobarlo, JSON.parse revienta y el usuario ve
    "Unexpected token '<'". Pasó de verdad: Cloudflare cortó una búsqueda larga
    y devolvió su página de error.
    """
    assert "async function leerJson" in HTML
    # ninguna llamada de lectura debe ir directo a .json() sin pasar por ahí,
    # salvo la del proveedor externo, que devuelve JSON incluso en su 502
    directas = [
        linea.strip()
        for linea in HTML.splitlines()
        if "await resp.json()" in linea and "proveedor" not in linea
    ]
    assert not directas, f"llamadas sin comprobar el formato: {directas}"


def test_se_avisa_que_la_redaccion_puede_tardar():
    assert "puede tardar varios minutos" in HTML
