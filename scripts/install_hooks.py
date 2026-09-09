"""Instala un hook de pre-commit que corre check.bat antes de cada commit."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HOOK = RAIZ / ".git" / "hooks" / "pre-commit"

CONTENIDO = """#!/bin/sh
# No usar `cmd.exe /c check.bat`: bajo Git Bash/MSYS su código de salida
# no siempre se propaga y el hook puede pasar en silencio aunque algo falle.
# Se invoca el python del venv directamente, paso a paso.
#
# El nombre del entorno NO se da por supuesto. Estaba fijado a "venv/" y en un
# equipo cuyo entorno se llamaba ".venv/" el hook bloqueaba TODOS los commits
# con "No such file or directory" — falla segura, pero por el motivo
# equivocado y sin decir cuál era. Si no aparece ninguno, el hook lo dice y
# corta: un hook que no encuentra con qué comprobar no debe dejar pasar nada.
PY=""
for CANDIDATO in venv/Scripts/python.exe .venv/Scripts/python.exe \\
                 venv/bin/python .venv/bin/python; do
    if [ -x "$CANDIDATO" ]; then PY="$CANDIDATO"; break; fi
done

if [ -z "$PY" ]; then
    echo "pre-commit: no encuentro el entorno virtual (probé venv/ y .venv/)." >&2
    echo "            Créalo con: py -3.12 -m venv venv" >&2
    exit 1
fi

"$PY" -m ruff check . || exit 1
"$PY" -m ruff format --check . || exit 1
"$PY" -m pytest tests/ -q || exit 1
exit 0
"""


def main() -> None:
    if not (RAIZ / ".git").exists():
        print("No hay repositorio git en", RAIZ)
        return
    HOOK.parent.mkdir(parents=True, exist_ok=True)
    HOOK.write_text(CONTENIDO, encoding="utf-8", newline="\n")
    HOOK.chmod(0o755)
    print(f"Hook instalado en {HOOK}")


if __name__ == "__main__":
    main()
