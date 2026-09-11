# CLAUDE.md — Aliado Libre

RAG legal colombiano libre y gratuito. Primera herramienta de Suite Legal Libre.

Antes de tocar nada, leé en este orden:

1. `docs/PROJECT_STATE.md` — qué funciona hoy, comandos, limitaciones.
   Verificado, no recordado.
2. `docs/PRINCIPIOS.md` — el modelo de producto (gratuito, sin registro,
   cobertura honesta). Decidido el 6-sep-2026.
3. `docs/DECISIONS.md` — las 13 decisiones técnicas y de método.
4. `docs/NEXT_STEPS.md` — la siguiente tarea concreta.
5. `CHANGELOG.md` — el detalle sesión a sesión, extenso y con el porqué.

## Las reglas que no se negocian

1. **Nunca inventar cobertura.** Si el índice no tiene algo, la app lo dice, y
   distingue "no está en el índice" de "no sé". Los huecos son información útil.
2. **No se guardan consultas ni se registra quién pregunta.** Está implementado
   como código, no prometido.
3. **No actualizar dependencias como higiene.** Las versiones están pinneadas a
   propósito: son las que construyeron el índice y midieron la calidad (D-05).
4. **Medir sobre datos apartados.** La mitad de prueba del banco está intacta
   para eso. No la toques para entrenar.

## La lección más cara del proyecto

**El hardware donde se genera es una variable del experimento.** Durante tres
días se sostuvo, con prueba estadística detrás, que una cuantización perdía
precisión frente a otra. Las respuestas de una se habían generado en GPU y las
de la otra en CPU. Al repetirlo bien, la diferencia desaparecía — y la
conclusión falsa casi triplica el tamaño de lo que se iba a distribuir.

Nunca compares corridas hechas en hardware distinto. Y cuando midas, di
"no se detecta diferencia con esta muestra", no "no hay diferencia".

## Dónde está el problema de verdad

En la **recuperación**, no en el LLM. Verificado: el embedding viejo truncaba a
128 tokens y el 76% de los fragmentos supera los 500 caracteres. No inviertas
esfuerzo en la capa que redacta mientras la recuperación no esté medida.

## Verificación antes de dar algo por bueno

```bash
./.venv/Scripts/python.exe -m pytest tests/ -q     # 344 esperadas, ~71 s
check.bat                                          # lint + formato + tests
```

## Secretos

Ninguno vive en el repo y ninguno debe añadirse. `ALIADO_INDICE_TOKEN` y
`HF_TOKEN` se leen del entorno. Si hace falta un archivo de credenciales, va a
`~/.aliado_libre/credenciales.json`, **nunca al proyecto**.

Antes de correr cualquier cosa que llame a una API de pago: estimá el costo y
confirmá con Fabián.
