# Licencias de Aliado Libre

El proyecto tiene tres capas y cada una tiene su régimen.

## 1. Código — GNU AGPL-3.0

Todo el código fuente de este repositorio se distribuye bajo la
**GNU Affero General Public License v3.0** (texto completo en `LICENSE`).

En la práctica: puedes usarlo, estudiarlo, modificarlo y redistribuirlo. Si lo
modificas y lo ofreces a otras personas, **también como servicio web**, debes
publicar el código fuente de tu versión bajo la misma licencia.

Copyright © 2026 Fabián Gulla.

## 2. Datos producidos por el proyecto — uso personal libre, uso comercial con licencia

Los datos que este proyecto genera **no** se publican bajo licencia libre:

- el índice de búsqueda (vectores, índice léxico y metadatos);
- la tabla de vigencia por documento (`index/vigencia_documentos.json`);
- los bancos de evaluación, las consultas agregadas y sus resultados.

Copyright © 2026 Fabián Gulla. Todos los derechos reservados, con estas
excepciones:

- **Uso personal, académico o sin ánimo de lucro**: permitido, citando
  "Aliado Libre", mediante la aplicación o el servicio público, dentro de sus
  límites de uso razonable.
- **Uso comercial o a escala** (integrarlo en un producto o servicio, reventa,
  consultas masivas o automatizadas por encima del límite gratuito): requiere
  una licencia o una clave de acceso de pago. Escribe a fabian.gulla@gmail.com.

La versión del índice publicada en Hugging Face el 7-sep-2026
(`Gullax/indice-legal-colombia`) conserva las condiciones con las que se
publicó. Las versiones posteriores se rigen por esta sección.

## 3. Corpus normativo — textos oficiales

Las leyes, decretos, resoluciones, conceptos y sentencias que contiene el índice
son textos oficiales del Estado colombiano. Su reproducción es libre según el
artículo 41 de la Ley 23 de 1982, con fidelidad a la edición oficial. Este
proyecto no reclama derechos sobre ellos.

Proceden de fuentes públicas (Función Pública, DIAN, Corte Constitucional,
Superintendencias, SIC y el repositorio `legalize-dev/legalize-co`, cuyo
pipeline es MIT). El catálogo de vigencias procede de datos.gov.co (conjunto
`fiev-nid6`, SUIN-Juriscol). El detalle de cada fuente está en `docs/fuentes.md`.

**Aliado Libre no es una fuente oficial.** Ante cualquier duda, prevalece el
texto publicado por la entidad emisora.

## Componentes de terceros

- **Modelo propio**: derivado de Qwen2.5-1.5B-Instruct (Apache-2.0). Se conserva
  su aviso de licencia al distribuirlo.
- **Modelos de búsqueda**: `intfloat/multilingual-e5-large` (MIT) y
  `BAAI/bge-reranker-v2-m3` (Apache-2.0), usados sin modificar.
- Las dependencias de Python conservan sus propias licencias
  (`requirements.txt`); todas son compatibles con la AGPL-3.0.

## Contribuciones

Quien aporte código acepta publicarlo bajo AGPL-3.0 y concede al titular del
proyecto permiso para relicenciarlo, de modo que el proyecto pueda ofrecer
también otras licencias sin perder la versión libre. Ver `CONTRIBUTING.md`.
