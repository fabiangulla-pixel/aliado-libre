# Contribuir a Aliado Libre

Gracias por el interés. Antes de abrir un pull request:

1. **Pruebas**: `.venv/Scripts/python.exe -m pytest tests/ -q` debe pasar entero,
   y `check.bat` (lint + formato + pruebas) también. Un cambio de comportamiento
   trae su prueba; una guarda nueva trae además su prueba negativa.
2. **Mediciones**: si tocas la recuperación, el prompt o el modelo, mide antes y
   después sobre la partición de desarrollo (`finetune/eval/lab_recuperacion.py`)
   y cambia **una sola variable** por experimento.
3. **Nada de secretos** en el repositorio: claves y tokens van al entorno o a
   `~/.aliado_libre/credenciales.json`.
4. **Nunca inventar cobertura**: si el índice no tiene algo, la aplicación lo
   dice. Ver `docs/PRINCIPIOS.md`.

## Licencia de tus aportes

Al enviar una contribución aceptas que:

- se publica bajo la **GNU AGPL-3.0**, como el resto del código; y
- concedes al titular del proyecto (Fabián Gulla) una licencia perpetua,
  mundial, gratuita e irrevocable para usar, modificar, sublicenciar y
  **relicenciar** tu aporte, incluso bajo otras licencias.

Lo segundo permite ofrecer el proyecto también con otras condiciones sin
dejar de publicarlo como software libre. Si no estás de acuerdo, dilo en el pull
request antes de que se fusione.

Seguridad: los fallos de seguridad no se reportan en issues públicos. Ver
`SECURITY.md`.
