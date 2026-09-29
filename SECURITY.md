# Seguridad

Aliado Libre es un proyecto experimental. Si encuentras una vulnerabilidad, **no
abras un issue público**: escribe a fabian.gulla@gmail.com con los pasos para
reproducirla. Respuesta en días, no en horas.

## Modelo de amenazas (29-sep-2026)

Un RAG jurídico tiene dos clases de daño: el técnico (credenciales, archivos) y el
jurídico (una respuesta que alguien aplica y no rige). El segundo es el más
probable, así que va primero.

| Riesgo | Control que existe | Dónde | Prueba |
|---|---|---|---|
| Respuesta basada en norma derogada o inexequible | vigencia por documento (nota oficial + SUIN-Juriscol); advertencia antepuesta si la respuesta calla; abstención si todo lo recuperado ya no rige | `index/vigencia.py`, `index/enrutador.py` | `tests/test_vigencia.py` |
| Cita o cifra inventada | verificador determinista de anclaje | `index/verificar_anclaje.py` | `tests/test_verificar_anclaje.py` |
| Respuesta sin evidencia presentada como fundamentada | `hay_respaldo` en la API; sin respaldo no se redacta | `gui/server.py` | `tests/test_gui_server.py` |
| Instrucciones incrustadas en un documento del corpus | fragmentos entre `<documento>…</documento>`; el prompt los declara material de consulta; un fragmento no puede cerrar el delimitador | `index/responder.py` | `tests/test_vigencia.py` |
| Argumentos manipulados en herramientas MCP | longitud de consulta y `max_resultados` acotados; ids validados con lista blanca de caracteres; ninguna herramienta lee rutas, ejecuta SQL arbitrario ni comandos | `mcp_server/server.py` | `tests/test_mcp_server.py` |
| Exposición de la clave de API del usuario | la clave llega por petición, se usa una vez, no se guarda y se borra de los mensajes de error | `index/proveedores.py` | `tests/test_clave_api.py` |
| Credenciales del proyecto en el repositorio | ninguna vive en el repo; van a `~/.aliado_libre/credenciales.json` o al entorno | — | revisión antes de cada push |
| Registro de consultas sensibles | no se guardan consultas ni se identifica a quien pregunta | `gui/server.py` | `tests/test_no_registro.py` |
| Cuerpos HTTP no drenados (conexión abortada en Windows) | drenaje único en `drenar_cuerpo.py`, con tope | `drenar_cuerpo.py` | `tests/test_servidor_indice.py` |
| Índice mezclado de dos corpus o troceos | huella del corpus y del troceo en los metadatos; el indexador se niega a reanudar si no coinciden | `reindexar_con_gpu.py` | `tests/test_indice_alterno.py` |

## Lo que NO está cubierto

- **Vigencia sin fuente**: una norma cuyo texto no trae nota y que SUIN no marca como
  derogada aparece como "sin nota". Eso no la hace vigente. Ejemplo medido: la Ley 33 de
  1986 (tránsito), que SUIN marca "Vigente".
- **Derogación tácita o parcial por artículo** que no esté anotada en el texto.
- **Ruta de nube**: la consulta y los fragmentos salen al proveedor que elija el usuario.
  La interfaz lo dice; no hay filtro automático de datos personales.
- **Escaneo de secretos automatizado** antes de publicar: hoy es revisión manual.
