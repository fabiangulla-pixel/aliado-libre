# Planes y monetización — borrador (29-sep-2026)

**Estado: aparcado a propósito.** Decisión de Fabián: primero el producto, después
la facturación. Pero el objetivo es explícito: habrá una versión gratuita, libre y
accesible para todo el mundo, **y el proyecto va a generar ingresos**. Este archivo
guarda el modelo pensado para no rehacerlo cuando se retome.

## Lo que ya está construido (y activo por defecto)

`servidor_indice/cuotas.py`, sin pasarela de pago todavía:

| Qué | Valor por defecto | Variable |
|---|---|---|
| Aporte voluntario sugerido (sin bloquear) | a partir de la consulta 16 del día | `ALIADO_TOPE_APORTE=15` |
| Bloqueo del anónimo | a partir de la consulta 31 del día | `ALIADO_TOPE_DIARIO_IP=30` |
| Enlace de pago / aporte | el correo del proyecto | `ALIADO_ENLACE_PAGO` |
| Claves de pago con tope, periodo y vencimiento | — | `ALIADO_CLAVES_API` |
| Uso de las claves persistido | — | `ALIADO_USO_CLAVES` |

`scripts/crear_clave_api.py` emite las claves de cada plan. La página cuenta las
"tandas" del mes en el navegador de la persona (nunca en el servidor) y sugiere la
membresía con más de 4 tandas o cerca de 100 consultas en el mes.

## El modelo pensado

1. **Gratis**: hasta 15 consultas al día sin nada; de 16 a 30, se pide un aporte
   voluntario; a partir de 31, bloqueo hasta medianoche.
2. **Pase de un día**: lo que cuesta un pasaje de TransMilenio (~3.200–3.600 COP;
   confirmar la tarifa vigente). Clave `pase-dia`.
3. **Membresía mensual**: ~9 USD al mes. Clave `mensual`.
4. **Pro**: 25 USD por usuario al mes, sin tope. Clave `pro`.
5. **Empresarial**: 200 USD al mes, sugerido desde 9 usuarios (9 × 25 = 225).
   Clave `empresarial --usuarios N`.
6. **Gold**: pago único de 1.000 USD, sin tope durante π años (1.147 días) desde
   la activación. Clave `gold`.

## Pendiente de decidir antes de cobrar

- **Incoherencia de la membresía mensual**: como estaba planteada (100 consultas al
  MES) da menos que el plan gratuito (hasta ~900 al mes). ¿100 al día? ¿100 por
  encima del cupo gratuito?
- **"Ilimitado" con uso razonable**: buscar cuesta casi nada, pero redactar por nube
  cuesta ~0,004 USD por respuesta. A 25 USD/mes el punto de equilibrio está en
  ~6.000 respuestas; conviene un tope de uso razonable escrito en los términos.
- **Figura jurídica y recaudo** (pendiente desde el 6-sep, `docs/RECAUDO.md`), RUT,
  **facturación electrónica** DIAN, **IVA 19%** en servicios digitales (¿precios con
  IVA incluido?), **derecho de retracto** (Ley 1480) en ventas a distancia.
- **Gold**: un pago anticipado por más de tres años es una obligación a largo plazo;
  definir qué pasa si el servicio cambia o cierra.
- **Pasarela**: para micropagos (el pase de un día) Nequi, Daviplata o PSE; con
  tarjeta la comisión se come buena parte de 3.500 COP.
- **Índice de Hugging Face del 7-sep**: sigue público (143 descargas). Pasarlo a
  acceso con registro antes de lanzar planes.

Consultar lo legal y lo tributario con un contador o abogado: este archivo no lo es.
