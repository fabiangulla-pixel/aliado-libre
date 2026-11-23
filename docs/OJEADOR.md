# OJEADOR y la Corte Suprema en Aliado Libre

OJEADOR (<https://ojeador.cortesuprema.gov.co/>) es el «Sistema Inteligente de
Consulta Jurisprudencial» de la Corte Suprema de Justicia (Oficina de
Tecnología, ©2026). Este documento resume qué se comprobó de él el
**23-nov-2026**, qué se tomó para Aliado Libre y cómo se mantiene.

## 1. Qué se sabe de OJEADOR, separado por solidez

### a. Observado directamente (23-nov-2026, unas 45 peticiones en total, espaciadas)

- **Aplicación de una sola página** (Next.js). Tiene `meta robots=noindex` y no
  publica `robots.txt`: la ruta devuelve la propia aplicación.
- **La aplicación habla con un servicio propio**,
  `buscadorjurisprudenciabackend.cortesuprema.gov.co` (FastAPI). Rutas vistas en
  su JavaScript: `/search/`, `/search/citaciones/{id}`, `/search/similar/{numerador}`,
  `/search/votos-separados/`, `/filters/`, `/autocompletar/`,
  `/document/descargar?path=`, `/providenciasFrecuentes/` y otras de
  estadística de uso (`/visitas/ingreso`, `/eventos/*`).
- **Búsqueda.** Acepta texto libre (`query_text`), búsqueda estructurada por
  campo (`field=Numerador&term=SL131-2026&match=equals`) y filtros: `especialidad`
  (sala), `fechaInicio`/`fechaFin`, `tipoProvidencia`, `ponente`,
  `claseActuacion`, `tema` y `cui`. La búsqueda exacta por número devolvió
  `mode: "structured"` y una sola coincidencia.
- **Fichas.** Campos por providencia:
  - identificación: `id`, `Hash`, `CUI` (radicado de 23 dígitos), `Ubicacion` (ruta del archivo), `Numerador`, `NombreArchivo`;
  - fecha y ponente: `FechaConsolidacionFirma` (fecha completa), `Ponente`, `TipoDePonente`;
  - clasificación: `Sala`, `Especialidad`, `TipoDeProvidencia`, `ClaseActuacion`;
  - contenido: `TemaTexto` (árbol de temas), `Leyesynormas`, `Decisiones`;
  - otros: `TieneVotoSeparado`, `phrase_fragments` (fragmentos que coinciden con la consulta), `texto_preview`.
- **Enlace a la ficha.** La aplicación construye `/caso/<numerador>` y agrega
  `?doc=<Hash>` para distinguir duplicados. Al ser una aplicación de una sola
  página, **responde 200 a cualquier numerador**, incluido uno inexistente
  (`ZZ99999-1901`). El enlace por sí solo no prueba que la providencia exista.
- **Archivo original.** `GET /document/descargar?path=<Ubicacion>` devolvió el
  PDF de SL131-2026: 20 páginas, `content-disposition: attachment`. Funciona
  como enlace directo, sin cabeceras especiales.
- **Relaciones.** `/search/citaciones/<id numérico>` devuelve `salientes` (73
  para SL131-2026, cada una marcada `resuelto`) y `entrantes` (5, con fecha y
  ponente). La sección «providencias relacionadas» (`/search/similar/`) se
  rotula en la propia aplicación así: *«Decisiones con contenido jurídico
  semejante. Esta relación es temática y no implica que una providencia cite
  a la otra.»*
- **Otras funciones.** Gacetas históricas (`/gacetas-historicas?q=`) y
  búsqueda en ellas. Favoritos y colecciones **en el navegador**: hasta 25
  favoritos y 10 colecciones de 25, según la ayuda. Exportación CSV de
  colecciones. Búsqueda por texto: `/resultados?q=`.
- **Volumen.** Con `limit=50` un año de una sala declara `total_documents:
  10000`, que parece un tope del servicio. Un tercero
  ([PR #117 de scrapperavanzado](https://github.com/CaptainLevi20/scrapperavanzado/pull/117))
  reporta lo mismo y que la Corte le respondió 429 con 6 descargas en paralelo.

### b. Documentado por la Corte

Solo el aviso de la portada y de la ayuda:

> «Herramienta de consulta y apoyo a la investigación jurídica. Los
> resultados y fragmentos destacados se seleccionan de forma automatizada; el
> texto oficial es el de cada providencia. Verifique la providencia completa y
> la vigencia de las normas antes de citarla.»

No hay cifras oficiales de cobertura en el sitio. Las que circulan (646.940
providencias, 288 tomos de gacetas) vienen de un video de terceros y **no se
verificaron**.

### c. Técnicamente posible, sin confirmar

- Recorrer el servicio por sala y mes para un inventario completo. No se hizo:
  sería una descarga masiva sin autorización.
- Que `/search/similar/` use una búsqueda semántica. Lo sugiere el nombre; no
  se probó.

### d. Requeriría autorización o una interfaz oficial

- **No hay API pública documentada**: el `/docs` del servicio responde 401.
- No hay términos de uso que autoricen la descarga masiva.

Por eso Aliado Libre **no depende de OJEADOR**: funciona igual sin red. Las
consultas al servicio son opcionales, a mano, pocas y espaciadas, y nunca
llevan consultas de usuarios. Cualquier ingesta masiva desde OJEADOR (el
reemplazo natural del buscador antiguo, que según el mismo tercero dejó de
recibir providencias en abril de 2026) debería pedirse a la Corte.

## 2. Qué se tomó para Aliado Libre (todo local)

| Función | Dónde | Datos |
|---|---|---|
| Reconocer y resolver citas de la Suprema (`SL131-2026`, `CSJ SL 131-2026`, `SL131 de 2026`, `SC016-2018`=`SC16-2018`; prefijos SL, SC, SP, AL, AC, AP, STL, STC, STP, ATL, ATC, AHL), referencias sin año (candidatos), radicado único y número interno («un radicado identifica el proceso, no la decisión») | `index/providencias.py`, `index/resolver_citas.py` | catálogo local |
| Ficha: corporación, sala, tipo, número, radicado (CUI o interno), fecha con su precisión («solo se conoce el año»), ponente, origen del texto (digital/OCR/mixto) y confianza media del OCR | `providencias.ficha()`, GUI «Ficha de la providencia», MCP | texto y metadatos de `data/raw/corte_suprema*.json` |
| Enlaces separados: ficha oficial y archivo original **solo si se verificaron**; si no, «Buscar en Ojeador» (búsqueda, no ficha) y el buscador general antiguo | `providencias.enlaces()` | `data/ojeador/verificacion.jsonl` (opcional) |
| Relaciones «cita a» / «es citada por» con contexto y estado (`confirmada`, `ambigua`, `no_resuelta`), sin rotularlas como precedente, reiteración ni cambio | `index/relaciones_suprema.db`, `/api/providencia`, MCP `relaciones_providencia` | texto completo del corpus |
| Filtros por sala, tipo y año (posfiltro sobre los primeros candidatos de la Suprema; la respuesta lo dice) | `/api/buscar?sala=&tipo_providencia=&anio_desde=&anio_hasta=` | catálogo local |
| Lectura: «fragmento n.º N del documento, no el documento completo», anterior/siguiente entre coincidencias, resaltado seguro | `gui/static/index.html` | — |
| Tablero: colecciones, notas propias, exportación con radicado/fecha/ponente/enlace/fragmento/nota, persistencia **solo si se marca** «Recordar en este equipo», «Borrar todo», datos versionados | `gui/static/index.html` | solo el navegador |
| Verificación de enlaces y comparación de cobertura | `scripts/ojeador.py verificar / muestrear / comparar` | servicio de OJEADOR (opcional) + catálogo |

## 3. Evidencia de las decisiones (23-nov-2026)

- **Fichas desde el texto**. 39.374 providencias (21.889 con texto digital,
  17.370 por OCR y 115 mixtas). Fecha completa leída del encabezado: 92,3 %
  (digital), 97,0 % (OCR) y 99,1 % (mixto). Radicado: 98,3 %, 99,7 % y 100 %.
  Contra OJEADOR, en 31 providencias al azar:
  - 30 verificadas y 1 ambigua (dos archivos con el mismo número);
  - fecha igual en 29 de 29 comparables;
  - radicado único igual en 3 de 3.
  Para SL131-2026, las 73 citas salientes que detecta Aliado Libre coinciden
  con las 73 de OJEADOR.
- **Citas** (`finetune/medir_citas_suprema.py`, 60 citas a providencias del
  índice escritas de 4 formas, índice de 3.296.273 fragmentos, configuración
  por defecto, CPU Intel con la máquina quieta):
  - la búsqueda sola ponía la providencia citada primera en 19/60 y entre
    las 5 primeras en 22/60;
  - el resolvedor la pone primera en **60/60**;
  - 10 de 10 citas inexistentes reciben «no está en el índice (no quiere
    decir que no exista)»;
  - **0 falsos positivos** del reconocedor en 180 consultas reales sin cita.
  Es un banco nuevo de citas exactas, no banco_prueba_200.
- **Cobertura**. Muestra oficial de 2025: 2 páginas al azar de 50 por sala.
  - Laboral: 9 de 100 identificadores en el índice. De las 11 sentencias,
    hay 9; los 58 fallos de tutela y los 31 autos, ninguno.
  - Civil: 0 de 97; la muestra son casi todas tutelas STC.
  La ingesta de la Suprema **solo trae sentencias de casación** (SL y SC);
  ese es el hueco grande, no la Sala Penal sola. Es una muestra por
  conglomerados de dos salas y un año: no se extrapola.

## 4. Cómo se mantiene

```bash
# catálogo y relaciones (local, ~35 s; tras cualquier cambio en data/raw/corte_suprema*.json)
.venv/Scripts/python.exe -m index.providencias --construir

# opcional, con red: verificar enlaces (pausa >= 1 s; por defecto 3 s; se detiene ante 429/403)
.venv/Scripts/python.exe scripts/ojeador.py verificar SL131-2026 --muestra 40

# opcional, con red: muestra oficial y comparación (la comparación no usa red)
.venv/Scripts/python.exe scripts/ojeador.py muestrear --sala LABORAL --desde 2025-01-01 --hasta 2025-12-31 --paginas 2
.venv/Scripts/python.exe scripts/ojeador.py comparar data/ojeador/muestra_laboral_2025-01-01_2025-12-31_s11.json

# evaluación de citas (carga el índice real)
.venv/Scripts/python.exe finetune/medir_citas_suprema.py 60 23
```

La verificación se lee al arrancar: no hace falta reconstruir el catálogo
después de `verificar`, solo reiniciar el servidor. No hay que reindexar
Chroma: la ficha se agrega al vuelo por `documento_id`.

## 5. Límites que siguen

- El índice no tiene tutelas, autos ni la Sala Penal de la Suprema, y casi
  nada de 2026: 46 providencias, porque el buscador antiguo dejó de recibir.
- «Es citada por» cuenta solo lo que está en el índice. OJEADOR ve 5
  entrantes para SL131-2026 y Aliado Libre ninguna, porque las providencias
  que la citan no están ingeridas.
- No se reconocen las citas antiguas por fecha y radicado («CSJ SL, 5 ago.
  2014, rad. 45678»).
- Los filtros son un posfiltro sobre los primeros 30-60 candidatos de la
  Suprema: pueden dejar fuera providencias que cumplen. La respuesta lo dice.
- El `.exe` distribuible usa el índice remoto. Sin `catalogo_suprema.json`
  al lado no muestra fichas, aunque tampoco falla: `index.providencias` va
  en `hiddenimports`.
