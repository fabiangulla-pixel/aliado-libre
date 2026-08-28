# Mapa de fuentes jurídicas colombianas

Estado de cada fuente investigada para Aliado Libre, con fecha de verificación
técnica (no solo búsqueda web). Última actualización: 28-ago-2026.

## ✅ Accesibles con contenido real confirmado

| Fuente | URL | Tipo de contenido | Notas técnicas |
|---|---|---|---|
| **Gestor Normativo** (Función Pública) | funcionpublica.gov.co/eva/gestornormativo | Legislación nacional: 1.601 leyes (1886-2019) + 7.404 decretos (1826-hoy) | HTML plano. Requiere `requests.Session()` con cookie de la home antes de pedir `norma.php` (curl solo falla por manejo de cookies, no por bloqueo). Encoding roto server-side (declara ISO-8859-1, sirve UTF-8 doble-codificado) — se corrige con `texto.encode('latin1').decode('utf-8')`. La sección "Vigencias" de cada norma trae el grafo de modifica/deroga/reglamenta ya estructurado, con enlaces a los IDs relacionados — no hace falta inferirlo. **Ingester funcionando** (`ingest/fuentes/gestor_normativo.py`). |
| **Corte Constitucional** (relatoría) | corteconstitucional.gov.co/relatoria | Sentencias, ~49.630 providencias indexadas | SPA Angular, pero tiene API JSON interna en `/relatoria/buscador_new/?accion=...`. Confirmado `accion=ver_total_providencias`. El `accion=` exacto para búsqueda de texto completo **no está mapeado aún**. ⚠️ El dominio comparte WAF con SUIN — tras pruebas repetidas devolvió "The URL you requested has been blocked"; probablemente rate-limit temporal, reintentar con pausas largas (5s+) entre requests. |
| **Consejo de Estado** | consejodeestado.gov.co | Jurisprudencia contencioso-administrativa | Buscador web accesible. Dos sistemas: SAMAI/Mi Relatoría (desde dic-2021) y sistema tradicional para lo anterior. Ingester aún no escrito. |
| **Supersociedades** (Tesauro) | tesauro.supersociedades.gov.co | +9.000 conceptos jurídicos catalogados por tema | Accesible públicamente. Ingester aún no escrito. |
| **DIAN** (normograma) | normograma.dian.gov.co/dian/compilacion | Doctrina tributaria compilada, 1987-hoy | Accesible, organizado por tipo/año/tema. Ingester aún no escrito. |
| **Superfinanciera** | superfinanciera.gov.co | Jurisprudencia + boletines jurídicos periódicos | Accesible. Ingester aún no escrito. |
| **SIC — jurisdiccional** | relatoria.sic.gov.co | 1.807 providencias por competencia desleal y propiedad industrial | App React que habla **directo con un Elasticsearch expuesto públicamente**: `relatoria.sic.gov.co/sic-relatoria-idx/_search` (acepta DSL completo: `match_all`, `size`, `from`, agregaciones). Metadata rica (tesauro, fechas, tipo de proceso). **Texto completo en PDF/DOCX vive en S3 (`prod-relatorias-document`), bucket NO público (403 directo)** — falta encontrar el endpoint de descarga que usa la propia web (probablemente firma URLs por backend, no capturado aún). |

## ⚠️ Con pista, requiere navegador real (SPA) o verificación adicional

| Fuente | URL | Estado |
|---|---|---|
| **Corte Suprema de Justicia** | consultaprovidencias.cortesuprema.gov.co/busqueda | SPA (Vue), responde 200 pero shell vacío. API interna no capturada aún. El enlace alterno de la home de CSJ cae en `ramajudicial.gov.co` y da 403 (mismo bloqueo que SUIN). |
| **SIC — doctrina/conceptos** | buscadorconceptos.sic.gov.co | API interna confirmada (`POST /api/consultar`, replicable sin navegador), pero el backend devuelve `num_resultados_total: 0` para cualquier consulta — índice caído o vacío del lado de la SIC. **Aclaración importante**: esta es la única fuente de normativa/circulares/conceptos propios de la SIC — `relatoria.sic.gov.co` (arriba) solo cubre decisiones jurisdiccionales, no normas. Reintentar más adelante. |
| **Diario Oficial** (Imprenta Nacional) | imprenta.gov.co/diario-oficial, jacevedo.imprenta.gov.co | Ambos responden 200 con contenido real (HTML tradicional, no SPA). No verificado si permite descarga/consulta masiva por fecha o solo consulta puntual vía formulario. |

## 🔴 Bloqueadas (firewall/WAF)

| Fuente | URL | Respaldo |
|---|---|---|
| **SUIN-Juriscol** | suin-juriscol.gov.co | HTTP 500 "blocked" o conexión TLS cortada, confirmado con curl, PowerShell y Playwright (headless y headful). Bloqueo a nivel de IP/fingerprint, no de JS. |
| **Rama Judicial — jurisprudencia** | jurisprudencia.ramajudicial.gov.co | HTTP 403. Mismo dominio afecta el buscador de la Corte Suprema. |

**Respaldo para SUIN**: repos GitHub con licencia MIT que ya extrajeron el corpus:
- `legalize-dev/legalize-co` — legislación + jurisprudencia (Constitucional, Consejo de Estado, Suprema vía secciones de SUIN), 79.197 commits, desarrollo activo.
- `scuervo91/leyes-colombianas` — legislación en Markdown con historial de reformas vía git, 1887-presente, ~93% de reformas reconstruidas (no 100%).

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
