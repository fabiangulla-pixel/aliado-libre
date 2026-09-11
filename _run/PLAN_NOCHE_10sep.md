# Plan de la noche del 10-sep-2026 (Fabian durmiendo)

Encargo: esperar a ParrillaPRO, reindexar, seguir trabajando hasta donde se
pueda, y apagar el PC al terminar.

## Orden

1. ESPERA a que terminen los 2 `banco_cli.py` del Boletin de hidrologia
   isotopica #3 (ParrillaPRO). No se toca nada suyo.
2. Apartar el indice roto -> `index/chroma_db.roto_9sep` (2,3 GB, NO se borra).
3. Reindexar (~849.000 fragmentos) + reconstruir FTS5, encadenado.
4. Medir recall@5 sobre `finetune/eval/banco_prueba_200.json`.
   Referencias: indice sano viejo 33,5% · indice roto del 9-sep 0,5%.
5. Si el recall es razonable, regenerar los 20 casos de la abogada desde el
   indice bueno (los de `revision_juridica_limpia_v2.html` salieron del roto).
6. Actualizar PROJECT_STATE, SESSION_LOG y memoria. Commit local.
7. Apagar el PC.

## Lo que NO voy a hacer

- **No hago push.** Fabian no lo ha autorizado y sigue sin autorizarlo.
- **No borro** el indice roto ni nada del trabajo de ParrillaPRO.
- **No apago** si queda algo corriendo o algo sin guardar (ver condiciones).

## Condiciones para apagar

Se apaga SOLO si todas se cumplen:
- Ningun `banco_cli.py` vivo (el trabajo de ParrillaPRO termino por su cuenta).
- Ningun `reindexar_con_gpu.py` vivo.
- `git status` limpio en aliado-libre (todo commiteado).
- Este informe y la memoria escritos.

Si el reindexado falla, se apaga igual, pero dejando el fallo escrito aqui y en
la memoria. Un fallo documentado cierra la noche; un proceso a medias no.

## Si algo se tuerce

- **CUDA out of memory**: LM Studio y Ollama tienen 12,8 GB de 16,3 GB de VRAM
  tomados. Primer remedio: bajar `batch_size` de 64 a 16 en
  `reindexar_con_gpu.py`. No se tocan los modelos que Fabian dejo cargados.
- **El reindexado muere**: reanuda solo; se relanza. El indice bueno se va
  construyendo encima de si mismo, no se pierde lo hecho.

## Estado al empezar

Commit `eb054ad`, 344 tests verdes, lint y formato limpios, arbol limpio.
8 commits locales sin subir.
