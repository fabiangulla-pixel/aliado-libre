# Principios del proyecto

Decidido el 6 de septiembre de 2026. Este documento existe para que las
decisiones no se reinterpreten con el tiempo, y para que quien llegue después
entienda **por qué** el código está hecho así.

## 1. Modelo Wikipedia: gratuito, sostenido por aportes voluntarios

No hay suscripción, no hay muro de pago, no hay versión "pro". El uso es
gratuito y el sostenimiento se busca por donación.

El aviso al usuario, literal, es:

> No te cobramos por hacer tus consultas, pero tu aporte voluntario garantiza
> que la herramienta se mantendrá en el tiempo, funcional y disponible para
> tantos colombianos como la necesiten.

**Pendiente sin resolver: el recaudo.** Falta decidir por dónde entra el dinero
(pasarela, cuenta, figura jurídica que lo reciba, y qué implicaciones
tributarias tiene en Colombia). Nada de esto está definido y no debe
improvisarse: es lo que convierte un proyecto en algo que responde ante otros.

## 2. Dos despliegues, con públicos distintos

| | Quién | Qué corre | Por qué |
|---|---|---|---|
| **Nube** | Usuarios externos | Índice y redacción en el servidor; se accede por navegador | Los equipos de la mayoría de abogados son modestos: 8 GB de RAM y discos llenos. Y buena parte del público al que se apunta solo tiene teléfono |
| **Local** | El autor | Todo en la máquina: índice, modelo, interfaz | Banco de pruebas personal. Permite experimentar sin tocar el servicio ni gastar en API |

La versión local **no se abandona**: es donde se mide, se rompe y se prueba
antes de publicar nada.

## 3. No se guardan consultas ni se identifica a quien pregunta

Quien usa esto está preguntando por su despido, su tutela, su deuda o su
arriendo. Eso es información sensible aunque la consulta parezca banal.

Reglas, y son **código, no promesas**:

- El servidor del índice **no escribe log de acceso**: ni IP, ni línea de
  petición, ni marca de tiempo por usuario (`servidor_indice/server.py`,
  `log_message`).
- Los errores se registran **por tipo de excepción**, nunca con traza
  completa: un traceback puede arrastrar el texto que escribió el usuario
  hasta el log.
- `tests/test_no_registro.py` falla si alguien reintroduce cualquiera de las
  dos cosas. Sin esa prueba, la promesa se rompe sola en el siguiente cambio.

Lo que no se guarda no se puede filtrar, ni entregar bajo requerimiento, ni
perder en una brecha.

## 4. Qué hace libre a este proyecto

No es que corra en la máquina del usuario. Un servicio alojado puede ser
perfectamente libre; casi toda la infraestructura libre del mundo lo es. Lo
que lo define aquí:

- El código es abierto y auditable.
- El índice completo es **descargable por cualquiera** (publicado en Hugging
  Face), no solo consultable a través de un servicio.
- Cualquiera puede levantar su propia instancia.
- No hay suscripción ni cobro por uso.
- No se venden ni se explotan los datos de nadie, porque no se guardan.

**Consecuencia de diseño: el proyecto debe sobrevivir a quedarse sin dinero.**
Si el servidor se apaga, el código sigue en GitHub y el índice sigue
descargable. Nadie queda sin nada por el hecho de que se acaben las
donaciones. Un servicio de pago no puede ofrecer eso.

## 5. Honestidad sobre la calidad

Las cifras de acierto **no se publican** hasta alcanzar el 90% de precisión
(decidido el 4-sep-2026). Mientras tanto, la interfaz advierte que la capa que
redacta está en calibración y que hay que verificar siempre la cita.

Esto no es ocultar: las mediciones se llevan al día en `docs/MEDICIONES.md`
(no versionado). Lo que se evita es publicar una cifra que invite a confiar
más de lo que corresponde.

Y hay un motivo local para ser especialmente estricto: en febrero de 2026 la
Corte Suprema de Justicia sancionó a un abogado por presentar un recurso con
diez sentencias inexistentes producidas por una IA (Auto AC739-2026). El
verificador determinista de anclaje (`index/verificar_anclaje.py`) existe por
eso.
