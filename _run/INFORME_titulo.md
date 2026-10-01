# Experimento: título antepuesto al codificar (ALIADO_ENCABEZADO=titulo)

Corpus 1199645cc8a5a1ce, mismas 95 anclas, misma GPU. Generado solo por
_run/medir_titulo.py al terminar el reindexado.

| partición | config | recall@1 | recall@5 | recall@10 | MRR@10 |
|---|---|---|---|---|---|
| dev | base híbrida | 15.9% | 27.3% | 34.1% | 0.211 |
| dev | base solo vectorial | 15.9% | 29.5% | 34.1% | 0.204 |
| dev | título híbrida | 9.1% | 20.5% | 31.8% | 0.147 |
| dev | título solo vectorial | 11.4% | 20.5% | 27.3% | 0.159 |
| test | base híbrida | 11.8% | 27.5% | 29.4% | 0.182 |
| test | base solo vectorial | 15.7% | 29.4% | 31.4% | 0.204 |
| test | título híbrida | 11.8% | 23.5% | 31.4% | 0.168 |
| test | título solo vectorial | 15.7% | 25.5% | 29.4% | 0.199 |
| todo | base híbrida | 13.7% | 27.4% | 31.6% | 0.196 |
| todo | base solo vectorial | 15.8% | 29.5% | 32.6% | 0.204 |
| todo | título híbrida | 10.5% | 22.1% | 31.6% | 0.158 |
| todo | título solo vectorial | 13.7% | 23.2% | 28.4% | 0.180 |

## Por perfil (todo, híbrida, recall@5)

| perfil | base | título |
|---|---|---|
| abogado_junior | 16/24 | 13/24 |
| adulto_mayor_informal | 0/8 | 0/8 |
| baja_alfabetizacion | 0/6 | 0/6 |
| ciudadano_medio | 3/19 | 2/19 |
| comerciante_practico | 1/15 | 1/15 |
| con_ruido_irrelevante | 1/5 | 1/5 |
| mensaje_telegrafico | 2/6 | 2/6 |
| semi_tecnico_impreciso | 3/12 | 2/12 |

**Top-5 por caso: el título gana 3 y pierde 8** (de 95).
