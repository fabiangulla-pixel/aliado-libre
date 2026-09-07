# DECISIONS — Aliado Libre

Complementa `docs/PRINCIPIOS.md` (decidido el 6-sep-2026), que sigue siendo la
fuente sobre el modelo de producto. Aquí quedan las decisiones **técnicas y de
método** para que no se reinterpreten ni se re-litiguen.

---

### D-01 — Modelo Wikipedia: gratuito, aportes voluntarios
Sin suscripción, sin muro de pago, sin versión "pro". Ver `docs/PRINCIPIOS.md`.
**El recaudo sigue sin resolver** y no debe improvisarse.

### D-02 — Sin registro y sin guardar consultas — como código, no como promesa
No se almacena quién pregunta ni qué pregunta. Está implementado, no es una
declaración de intenciones.

### D-03 — Cobertura honesta: los huecos son información útil
El proyecto no pretende cubrir toda la data jurídica de Colombia. Cuando el
índice no tiene algo, la app lo dice, y **distingue "no está en el índice" de
"no sé"**. Nunca inventar. Las fuentes cubiertas y las que no, con el motivo,
están en `docs/fuentes.md`.

### D-04 — Verificador determinista sobre la respuesta redactada
Un verificador comprueba que cada número de norma, artículo, plazo y cifra de la
respuesta esté en los fragmentos recuperados, y marca lo que no encuentre. Es la
salvaguarda que permite publicar algo que todavía está en calibración.

### D-05 — Versiones fijadas a propósito
`requirements.txt` está pinneado porque esas son las versiones que construyeron
el índice y midieron la calidad. Sin fijarlas, una instalación de dentro de tres
meses trae otra cosa y **las mediciones dejan de ser reproducibles sin que nadie
se entere**. No "actualizar dependencias" como tarea de higiene.

### D-06 — Medir sobre datos apartados, antes de ajustar
El banco de evaluación tiene mitad dev y mitad prueba. Para afinar el embedding
solo se usa la mitad de dev; **la de prueba queda intacta** para poder medir
después. Sin esto no hay forma de saber si una mejora es real.

### D-07 — El hardware donde se genera es una variable del experimento
Lección cara: durante tres días se sostuvo que Q4_K_M perdía precisión frente a
q8_0, con prueba estadística. La comparación no era válida — una se generó en
GPU y la otra en CPU. Repetida con ambas en CPU, la diferencia desaparece.
**Cambiar dos cosas a la vez casi triplica el tamaño de lo que se iba a
repartir.** Nunca comparar corridas hechas en hardware distinto.

### D-08 — Se distribuye Q4_K_M (940 MB), no q8_0 (2.950 MB)
Consecuencia de D-07. Dicho con honestidad: "no se detecta diferencia" con 115
preguntas pareadas **no es** "no hay diferencia"; una caída pequeña sería
invisible a este tamaño de muestra.

### D-09 — Lo medido y descartado se documenta igual que lo que funciona
La reescritura de consultas y el filtro de palabras vacías están documentados
con sus cifras aunque no se adoptaran (o se adoptaran por otra razón). Evita que
alguien los reintente dentro de seis meses.

### D-10 — El filtro de palabras vacías se queda aunque no mejore el acierto
Gana 20× en velocidad con acierto estadísticamente igual. Se queda porque el
coste escalaba con la longitud de la pregunta: castigaba con 15 s de espera
justo a quien más rodeos da, es decir **al usuario menos experto**. Criterio de
equidad, no de métrica.

### D-11 — El nombre de los embeddings se lee de un solo sitio
Servidor y buscador pedían modelos distintos; como en el servidor se prohíbe
descargar en caliente, habría arrancado y muerto el día del despliegue. Ahora
hay un test que impide que vuelvan a separarse.

### D-12 — El proyecto cambiará de nombre
Candidatos y disponibilidad verificable en `docs/NOMBRE.md`, con la advertencia
de que **un dominio sin uso no es un dominio libre**.

### D-13 — El cuello de botella es la recuperación, no el LLM
Verificado, no supuesto: el embedding viejo truncaba a 128 tokens y el 76% de
los fragmentos supera los 500 caracteres. No invertir esfuerzo en la capa
generativa mientras la recuperación no esté resuelta y medida.
