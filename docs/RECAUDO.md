# Recaudo de aportes voluntarios — opciones, no decisión

Investigado el 6-sep-2026. Este documento **no decide nada**: reúne las vías
posibles con lo que se pudo verificar y marca lo que falta confirmar. La
decisión implica figura jurídica y obligaciones tributarias en Colombia, así
que conviene tomarla con asesoría, no desde aquí.

## El punto de partida

El modelo elegido es tipo Wikipedia: uso gratuito, sin suscripción, sostenido
por aportes voluntarios. El costo fijo del servicio es bajo —del orden de
10-40 USD/mes según el tráfico— así que el recaudo no necesita ser grande; lo
que necesita es ser **legal, sencillo de operar y transparente**.

## Vías internacionales (pensadas para software libre)

**GitHub Sponsors.** Verificado: Colombia está entre las más de 140 regiones
soportadas para *recibir* fondos. Sin comisión cuando el patrocinador es una
cuenta personal; hasta 6% cuando es una organización (3% de procesamiento de
tarjeta + 3% de servicio, y ese primer 3% se evita con facturación). Es la vía
de menor fricción para un proyecto que ya vive en GitHub.
*Falta confirmar*: el método de pago concreto hacia Colombia y qué formularios
tributarios exige.

**Open Collective.** Su ventaja no es cobrar, es el **anfitrión fiscal**: una
entidad ya constituida recibe el dinero, lo administra y publica cada gasto.
Eso resuelve de golpe la figura jurídica y encaja con la transparencia que el
proyecto promete. Open Source Collective es anfitrión aprobado para GitHub
Sponsors, así que ambas vías se pueden combinar.
*Falta confirmar*: si aceptan un proyecto con mantenedor en Colombia y qué
porcentaje cobran.

**Otras conocidas del ecosistema**: Ko-fi, Patreon, Liberapay. Menos alineadas
con software libre que las dos anteriores, pero más simples.

## Vías locales

Pasarelas que operan en Colombia: **PayU Latam, ePayco, Mercado Pago, PlaceToPay,
Zona Pagos**, además de PayPal. Dan cobertura a medios de pago locales (PSE,
Nequi, efectivo), que es exactamente lo que usaría un donante colombiano.
*Falta confirmar*: comisiones reales y si permiten recibir donaciones sin ser
entidad sin ánimo de lucro.

## Lo tributario — la parte que hay que consultar

Lo verificado, y conviene tomarlo como señal de alerta y no como conclusión:

- Recibir donaciones **incrementa el patrimonio del receptor** y puede generar
  **impuesto de ganancia ocasional**. No es dinero "libre" por ser donación.
- **No hay beneficio tributario** para quien dona a un proyecto así en
  Colombia, salvo que la receptora sea una entidad del **Régimen Tributario
  Especial** que expida certificado de donación.
- El crowdfunding de donación es legal (el Decreto 1357 de 2018 regula la
  financiación colaborativa) pero **no está regulado específicamente**.

Traducido: **recibir como persona natural es lo más simple de arrancar y lo
peor de sostener.** Si el recaudo crece, la vía razonable es una entidad sin
ánimo de lucro en Régimen Tributario Especial, o un anfitrión fiscal
internacional que asuma esa función.

## Recomendación para empezar, sin cerrar puertas

1. **GitHub Sponsors** como primera vía: verificado que Colombia está
   soportada, comisión baja o nula, y coherente con un proyecto libre.
2. **Publicar las cuentas.** Si se pide dinero apelando a la transparencia, hay
   que mostrar en qué se gasta. Los costos de este proyecto son pocos y
   públicos por naturaleza (servidor, dominio, respaldos): una página con el
   gasto mensual real es barata de mantener y es el mejor argumento.
3. **No pedir dinero hasta que la herramienta sirva.** Hoy la calidad de la
   redacción está por debajo del umbral que nos fijamos. Pedir aportes antes de
   eso gasta la credibilidad que es el único activo del proyecto.
4. **Consultar con un contador colombiano** antes de recibir el primer peso.
   Esta parte no se resuelve leyendo.

## Qué NO hacer

- Recibir donaciones en una cuenta personal sin registrar el ingreso.
- Prometer beneficios tributarios al donante: hoy no existen para este caso.
- Condicionar funciones al aporte. Eso sería suscripción con otro nombre, y
  contradice el modelo elegido (ver `docs/PRINCIPIOS.md`).
