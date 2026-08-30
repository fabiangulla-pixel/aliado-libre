# Mapa de fuentes jurídicas colombianas

Estado de cada fuente investigada para Aliado Libre, con fecha de verificación
técnica (no solo búsqueda web). Última actualización: 28-ago-2026.

**Patrón recurrente a explotar en fuentes nuevas**: varios sitios .gov.co con
frontend SPA (React/Vue/Angular) hablan directo con un **Elasticsearch expuesto
públicamente** (sin proxy que oculte la consulta), en vez de una API propia. Ya
confirmado en SIC y Supersociedades. Vale la pena, para cada SPA nueva, capturar
las llamadas de red con Playwright durante una búsqueda de prueba antes de asumir
que hace falta navegador para todo — si aparece un dominio tipo `admin.es.*` o
`*.es.prod.*` respondiendo a `_search`, es oro: acceso a consultas DSL completas.

## ✅ Accesibles con contenido real confirmado

| Fuente | URL | Tipo de contenido | Notas técnicas |
|---|---|---|---|
> **Techo del método BFS confirmado (28-ago-2026)**: el crawler vía "Vigencias" se
> estabilizó en ~2.381 normas tras tres intentos de ampliar semillas (25 decretos
> sectoriales: +15 docs; 6 códigos generales: +2 docs; 9 leyes nombradas: +3 docs).
> Las leyes/códigos individuales (a diferencia de los "decretos únicos reglamentarios"
> modernos) tienen seguimiento de "Vigencias" muy pobre en el sitio — el contenido en
> sí es valioso y ya está en el corpus, pero no abre más camino de BFS. Para crecer
> más allá de esto hace falta otro método (enumeración de rango de IDs, o un listado
> oficial de normas por tipo/año en vez de seguir el grafo de modificaciones).

| **Gestor Normativo** (Función Pública) | funcionpublica.gov.co/eva/gestornormativo | Legislación nacional: 1.601 leyes (1886-2019) + 7.404 decretos (1826-hoy) | HTML plano. Requiere `requests.Session()` con cookie de la home antes de pedir `norma.php` (curl solo falla por manejo de cookies, no por bloqueo). Encoding roto server-side (declara ISO-8859-1, sirve UTF-8 doble-codificado) — se corrige con `texto.encode('latin1').decode('utf-8')`. La sección "Vigencias" de cada norma trae el grafo de modifica/deroga/reglamenta ya estructurado, con enlaces a los IDs relacionados — no hace falta inferirlo. **Ingester funcionando** (`ingest/fuentes/gestor_normativo.py`). |
| **Corte Constitucional** (relatoría) | corteconstitucional.gov.co/relatoria | Sentencias, ~49.630 providencias indexadas | SPA Angular, pero tiene API JSON interna en `/relatoria/buscador_new/?accion=...`. Confirmado `accion=ver_total_providencias`. El `accion=` exacto para búsqueda de texto completo **no está mapeado aún**. ⚠️ El dominio comparte WAF con SUIN — tras pruebas repetidas devolvió "The URL you requested has been blocked"; probablemente rate-limit temporal, reintentar con pausas largas (5s+) entre requests. |
| **Consejo de Estado** | consejodeestado.gov.co | Jurisprudencia contencioso-administrativa | Buscador web accesible. Dos sistemas: SAMAI/Mi Relatoría (desde dic-2021) y sistema tradicional para lo anterior. Ingester aún no escrito. |
| **Supersociedades** (Tesauro) | tesauro.supersociedades.gov.co | +10.000 conceptos jurídicos y jurisprudencia mercantil | App Vite/SPA que habla directo con Elasticsearch expuesto públicamente: `admin.es.prod.ssociedades.nuvu.cc/index_thesaurus/_search`. **Mejor que SIC: el texto completo viene embebido** en `documento_principal.contenido_archivo`, sin depender de PDFs en S3. Metadata rica: descriptores del tesauro, fuentes jurídicas citadas (con estado de vigencia), tipo de contenido. **Ingester funcionando** (`ingest/fuentes/supersociedades.py`), sin BFS (paginación simple por `from`/`size`). |
| **DIAN** (normograma) | normograma.dian.gov.co/dian/compilacion | Doctrina tributaria compilada, 1987-hoy | Accesible como HTML plano (no bloqueado, no SPA), pero el listado real de conceptos/doctrina se carga como árbol dinámico vía JS (`verMas_AddListenerArbol.js`, `onLoadPaginaArbol_aux.js`), no encontrado aún en HTML estático ni en un endpoint JSON obvio. Requiere una pasada con Playwright para capturar cómo se puebla el árbol antes de poder escribir el ingester. |
| **Superfinanciera** | superfinanciera.gov.co | Jurisprudencia + boletines jurídicos periódicos | Accesible. Ingester aún no escrito. |
| **SIC — jurisdiccional** | relatoria.sic.gov.co | 1.807 providencias por competencia desleal y propiedad industrial | App React que habla **directo con un Elasticsearch expuesto públicamente**: `relatoria.sic.gov.co/sic-relatoria-idx/_search`. Metadata rica (tesauro, fechas, tipo de proceso). El texto vive en PDF en S3 (`prod-relatorias-document`), bucket no público directo, **pero resuelto**: hay un endpoint Lambda público sin autenticación, `m0s03uyzg3.execute-api.us-east-1.amazonaws.com/prod/get-signed-url/<ruta_s3>`, que devuelve una URL S3 firmada temporal para cualquier ruta — capturado interceptando la llamada real del frontend al hacer clic en un resultado. **Ingester funcionando** (`ingest/fuentes/sic.py`), extrae texto de PDF con `pypdf`. |
| **Corte Constitucional** | corteconstitucional.gov.co/relatoria | ~49.639 providencias (1992-hoy) | API JSON interna en `/relatoria/buscador_new/`. El input real es `#textoBuscador` + botón "Buscar" (no Enter directo), dispara `accion=search` con `searchOption/fini/ffin/buscar_por/maxprov/slop/tipo=json`. Con `buscar_por` vacío y `maxprov` alto (2000+), un solo request trae TODAS las providencias de un año — ~35 requests cubren el corpus completo, no hace falta paginar por documento. `prov_sintesis` ya trae un resumen jurídico sustancial sin petición adicional. **Ingester funcionando** (`ingest/fuentes/corte_constitucional.py`). ⚠️ Este dominio bloqueó temporalmente por WAF tras pruebas repetidas en una sesión anterior — usar pausas generosas (2s+) entre requests. |
| **DIAN** (normograma) | normograma.dian.gov.co/dian/compilacion | Doctrina/normativa/jurisprudencia tributaria, aduanera y cambiaria compiladas | Resuelto (29-ago-2026): **no hace falta Playwright**. Cada materia tiene una página estática (`tributario.html`, etc.) cuyas "opciones" (normativa/doctrina/jurisprudencia), leídas desde `openClosePanelArbolOpcion_aux.js`, cargan fragmentos HTML también estáticos `<pagina>_parte_NN.html` (N=01,02...) con los enlaces a cada documento en `docs/*.htm`. Cada documento trae el texto completo en `<div class="panel-documento">`, mismo mojibake ISO-8859-1/UTF-8 que Gestor Normativo. **Ingester funcionando** (`ingest/fuentes/dian.py`), cubre tributario/aduanero/cambiario. |
| **Superfinanciera** | superfinanciera.gov.co | Conceptos jurídicos y jurisprudencia financiera, **18.569 registros** en el catálogo | Resuelto (29-ago-2026): el enlace "Conceptos y Jurisprudencia" apunta a un **buscador bibliográfico clásico ABCD/ISIS** (`ABCD/superfinanciera/php/buscar_integrada.php?base=juris`), no una SPA. Paginación simple `desde`/`count` (⚠️ `desde` es 1-indexado: `desde=0` devuelve el formulario vacío, no un error). Cada registro trae metadata rica (resumen, temas/materias, documento fuente) y casi siempre un enlace "Archivo de texto" descargable (`loader.php?...idFile=NNN`) con el contenido completo. **Ingester funcionando** (`ingest/fuentes/superfinanciera.py`). |
| **Corte Suprema de Justicia** | consultaprovidencias.cortesuprema.gov.co | Providencias de las 4 salas: Civil (~109k), Laboral (~302k), Penal (~218k), Tutelas (~394k) según conteo con comodín | Resuelto (29-ago-2026), contradice el hallazgo previo de "SPA con shell vacío": el frontend Vue habla con un **backend GraphQL propio no documentado antes**, `consultaprovidenciasbk.cortesuprema.gov.co/api`, sin autenticación. `getSearchResult` lista resultados por Sala+término (el comodín `"*"` trae TODO el corpus de la sala; `""` vacío da 0), `getContentSearch` trae el texto completo ya extraído del PDF/DOCX dado el `onlinePath`. Requiere headers `Origin`/`Referer` del frontend oficial (si no, 502) y `verify=False` (cadena de certificados incompleta, igual que otros .gov.co del proyecto). **Ingester funcionando y verificado con texto real** (`ingest/fuentes/corte_suprema.py`), con reintentos porque el backend es inestable (502 intermitente incluso con headers correctos, en ráfagas de varios minutos — parece un proxy con poca capacidad, no un bloqueo). **Escala pendiente**: son >1M resultados brutos entre las 4 salas (con duplicado .pdf/.docx por documento, deduplicado en el ingester); ingestar el corpus completo implica cientos de miles de llamadas a `getContentSearch` — usar `max_documentos` para escalar por lotes con checkpoint, como Gestor Normativo. |

## ⚠️ Con pista, requiere navegador real (SPA) o verificación adicional

| Fuente | URL | Estado |
|---|---|---|
| **Corte Suprema de Justicia** | consultaprovidencias.cortesuprema.gov.co/busqueda | SPA (Vue), responde 200 pero shell vacío. API interna no capturada aún. El enlace alterno de la home de CSJ cae en `ramajudicial.gov.co` y da 403 (mismo bloqueo que SUIN). |
| **Consejo de Estado** | consejodeestado.gov.co/buscador-de-jurisprudencia2 | El buscador "tradicional" embebe un iframe que apunta a `jurisprudencia.ramajudicial.gov.co` (el dominio ya bloqueado) o a una IP interna (`190.217.24.55:8080`), ambos inaccesibles. **SAMAI** (samai.consejodeestado.gov.co, sistema desde dic-2021) resultó ser el portal de gestión de casos para abogados/litigantes, NO un buscador público — la mayoría de sus recursos (JS, imágenes, CSS clave) devuelven 403 sin sesión autenticada. Un link de descarga de providencia encontrado en la home (`samaicore.consejodeestado.gov.co/api/DescargarProvidenciaPublica/...`) también dio 403 — parece requerir un token de sesión generado por el flujo de búsqueda, no reutilizable directamente. **Reintentado 29-ago-2026**: encontrada una tercera vía pública no documentada antes, `samai.consejodeestado.gov.co/TitulacionRelatoria/BuscadorProvidenciasTituladas.aspx` ("Mi Relatoría", ASP.NET WebForms clásico con `__VIEWSTATE`, en teoría scrapeable con requests). Responde 200 en carga inicial, pero **el primer postback (clic en el botón "Consejo Estado" del filtro de corporación) devuelve 403 de un Azure Application Gateway** — mismo patrón de bloqueo por WAF que el resto del ecosistema de Rama Judicial/Consejo de Estado, esta vez confirmado a nivel de interacción (POST/postback), no solo de carga de recursos estáticos. Cerrado de nuevo; el bloqueo parece estar a nivel de infraestructura compartida (Azure WAF) más que de una URL específica — no vale la pena seguir probando URLs nuevas dentro del mismo dominio/infraestructura. |
| **SIC — doctrina/conceptos** | buscadorconceptos.sic.gov.co | API interna confirmada (`POST /api/consultar`, replicable sin navegador), pero el backend devuelve `num_resultados_total: 0` para cualquier consulta — índice caído o vacío del lado de la SIC. **Aclaración importante**: esta es la única fuente de normativa/circulares/conceptos propios de la SIC — `relatoria.sic.gov.co` (arriba) solo cubre decisiones jurisdiccionales, no normas. Reintentar más adelante. |
| **Diario Oficial** (Imprenta Nacional) | imprenta.gov.co/diario-oficial, jacevedo.imprenta.gov.co | Ambos responden 200 con contenido real (HTML tradicional, no SPA). No verificado si permite descarga/consulta masiva por fecha o solo consulta puntual vía formulario. |

## 🔴 Bloqueadas (firewall/WAF)

| Fuente | URL | Respaldo |
|---|---|---|
| **SUIN-Juriscol** | suin-juriscol.gov.co | HTTP 500 "blocked" o conexión TLS cortada, confirmado con curl, PowerShell y Playwright (headless y headful). Bloqueo a nivel de IP/fingerprint, no de JS. |
| **Rama Judicial — jurisprudencia** | jurisprudencia.ramajudicial.gov.co | HTTP 403. Mismo dominio afecta el buscador de la Corte Suprema. |

**Respaldo para SUIN**: repos GitHub que ya extrajeron el corpus:
- `legalize-dev/legalize-co` — legislación + jurisprudencia (Constitucional, Consejo de Estado, Suprema vía secciones de SUIN), 79.197 commits, desarrollo activo. **Clonado en superficie (`--depth 1`) el 29-ago-2026** a `data/respaldo_legalize_co/` (71.903 archivos, ~2GB, ignorado en `.gitignore` — es un respaldo de datos, no código propio). Licencia real (verificada en su `LICENSE`, GitHub lo marca como "Other" porque el archivo mezcla dos licencias): el **pipeline** que genera el repo es MIT (`legalize-dev/legalize-pipeline`), el **contenido** son textos oficiales de dominio público. Aún no integrado a un ingester — es solo el respaldo crudo; falta escribir `ingest/fuentes/legalize_co_github.py` que lea el Markdown con YAML front matter y lo convierta a `Documento`.
- `scuervo91/leyes-colombianas` — legislación en Markdown con historial de reformas vía git, 1887-presente, ~93% de reformas reconstruidas (no 100%). No clonado aún (menor prioridad que legalize-co, que ya cubre más fuentes).

## ❌ Débil, disperso o sin investigar a fondo

- **Ministerio del Trabajo**: sin repositorio propio de conceptos jurídicos, doctrina laboral dispersa en boletines.
- **Congreso / Gaceta del Congreso**: sin API oficial confirmada. Pista: "Congreso Visible" (Uniandes) tiene API propia en `apicongresovisible.uniandes.edu.co`, sin verificar.
- **Consejo Superior de la Judicatura / Comisión Nacional de Disciplina Judicial**: no investigado.
- **Otras superintendencias** (Salud, Transporte, Puertos, Notariado y Registro, Economía Solidaria, Vigilancia): no investigadas.
- **Normativa territorial** (ordenanzas departamentales, acuerdos municipales): no investigado, volumen muy disperso (miles de entidades territoriales).
- **Jurisprudencia de tribunales y juzgados** (1ª y 2ª instancia, fuera de altas cortes): sin repositorio público centralizado conocido — volumen enorme, fuera de alcance realista para v1.

## datos.gov.co (Socrata) — solo metadata/índice, no texto completo

Útiles como índice/complemento, ninguno trae el texto embebido:

- `fiev-nid6` — índice de normas SUIN-Juriscol
- `v2k4-2t8s` — sentencias Corte Constitucional (ponente, sala, tipo, fecha, salvamentos de voto)
- `88h2-dykw` — normativa nacional Presidencia (URL + título + fecha, desde 2016)
- `shrb-iwqu` — jurisprudencia indígena Consejo de Estado (desde 1920)
- `4bku-d9az` — actuaciones judiciales MinJusticia ante Corte Constitucional (2023-2025)
