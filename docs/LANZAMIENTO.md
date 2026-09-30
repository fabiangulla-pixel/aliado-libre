# Lanzamiento de la beta pública (producto mínimo viable)

Decidido el 29-sep-2026: **Juris-consulta ColombIA**, servida desde el PC de
Fabián por Cloudflare Tunnel, gratis con límites, con 3 respuestas redactadas por
IA al día y un tope de gasto mensual. Pagos aparcados (`docs/PLANES.md`).

## Arrancar

```powershell
winget install --id Cloudflare.cloudflared      # una sola vez
powershell -ExecutionPolicy Bypass -File scripts\lanzar_publico.ps1
```

El script levanta `gui/server.py` en modo público (`gui/publico.py`) y un túnel
rápido. La URL `https://…trycloudflare.com` **cambia en cada arranque**: sirve para
una beta con enlace compartido a mano, no para anunciar.

## Qué hay que saber de servir desde el PC

- **El servicio vive mientras el PC esté encendido y despierto.** Desactivar la
  suspensión mientras corre (Configuración → Sistema → Energía).
- **El PC trabaja para otros**: cada consulta usa la GPU para la búsqueda. Si se
  entrena o reindexa a la vez, la web va más lenta.
- **Seguridad**: el servidor escucha solo en 127.0.0.1; no se abre ningún puerto
  del router y la IP de la casa no se publica. Lo único expuesto es la web
  (búsqueda, estado, fuentes, páginas estáticas y la redacción con la clave que
  traiga el propio usuario). Nada lee rutas arbitrarias.
- **Norton** intercepta TLS en este equipo: si la redacción falla con errores de
  certificado, ver `confianza_tls.py`.

## Configuración (variables que fija el script)

| Variable | Valor | Qué hace |
|---|---|---|
| `ALIADO_TOPE_APORTE` | 15 | desde la consulta 16 del día se pide un aporte |
| `ALIADO_TOPE_DIARIO_IP` | 30 | desde la 31, pausa hasta medianoche |
| `ALIADO_REDACCIONES_DIARIAS` | 3 | respuestas redactadas por IA gratis al día |
| `ALIADO_TOPE_GASTO_MES_USD` | 10 | tope de gasto de IA del mes; al llegar, se pausa la redacción |
| `ALIADO_ENLACE_PAGO` | (correo) | a dónde apunta el pedido de aporte |

10 USD/mes ≈ 2.500 respuestas redactadas con Haiku 4.5 (~0,004 USD cada una).

## Antes de compartir el enlace (lista de salida)

1. [ ] Revisión humana de las abstenciones (`finetune/eval/revision_abstenciones.html`)
   y de los 20 casos (`revision_humana.html`): es lo que dice si las respuestas
   sirven.
2. [ ] Leer y ajustar `gui/static/terminos.html` y `privacidad.html` (borradores;
   idealmente con un abogado).
3. [ ] Probar desde el celular con datos móviles (otra red).
4. [ ] Decidir el enlace de aporte (`ALIADO_ENLACE_PAGO`): Nequi, Daviplata o PSE.
5. [ ] Pasar el índice de Hugging Face del 7-sep a acceso con registro.

## Después de la beta

- URL fija: registrar el dominio y crear un túnel con nombre
  (`cloudflared tunnel create …`), o migrar a un VPS de 16 GB (~15-30 EUR/mes).
- Pasarela de pago y planes (`docs/PLANES.md`) cuando exista la figura jurídica.
