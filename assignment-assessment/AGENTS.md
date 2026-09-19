# AGENTS.md — Evaluación de trabajos de grupo

Guía para agentes que trabajen en `assignment-assessment/`. Ver también el
[`AGENTS.md` de la raíz](../AGENTS.md) y, para el contexto de cómo se crearon los
repositorios que acá se evalúan,
[`assignment-preparation/AGENTS.md`](../assignment-preparation/AGENTS.md).

## Qué hay implementado

Dos piezas encadenadas por un archivo:

1. **`clone_repos.py`** descarga un clon por grupo del roster en el directorio que
   indique el operador y escribe ahí `clones.json`, el manifiesto de la corrida.
2. **La skill [`preguntas-revision`](../.claude/skills/preguntas-revision/)**, en la
   raíz del repositorio, lee ese manifiesto y escribe las minutas de revisión en
   `output/<slug-curso>/<tarea>/grupo-XX/QUESTIONS.md`. Cada minuta trae **tres
   problemas candidatos** de 10 puntos, con sub-partes definidas por un schema de
   `.claude/skills/preguntas-revision/schemas/`; el docente marca uno con `[x]` y
   ese pasa a la etapa siguiente (el enunciado para los estudiantes). Los problemas
   son autocontenidos porque el estudiante no tendrá ni el enunciado de la tarea ni
   su código a la vista.
3. **La skill [`preparar-iet`](../.claude/skills/preparar-iet/)** toma el problema
   marcado en cada `QUESTIONS.md` y escribe en el mismo directorio `STATEMENT.md`
   (enunciado para los estudiantes), `SOLUTION.md` (pauta para los ayudantes) y sus
   PDF, renderizados con un navegador Chromium headless desde un HTML que genera el
   propio script. `QUESTIONS.md` es la fuente: los arreglos van ahí y se regenera.
4. **La skill [`preparar-impresion-iet`](../.claude/skills/preparar-impresion-iet/)**
   concatena los `STATEMENT.pdf` en un solo PDF a doble cara, en orden de grupo,
   con una copia por integrante del roster y páginas en blanco de relleno, tras
   validar que ningún estudiante del roster quede sin enunciado. Usa `pdfinfo`,
   `pdfunite` o `gs` por subproceso.

El manifiesto es la única interfaz entre las dos. Si le agregas un campo, hazlo
aditivo: la skill lee lo que necesita y el archivo de una corrida anterior tiene que
seguir sirviendo.

### Módulos

| Archivo | Responsabilidad |
|---|---|
| `config.py` | Carga `course.toml` y publica sus valores como constantes. Resuelve rutas: las entradas contra `REPO_ROOT`, las salidas contra `BASE_DIR`. |
| `roster_loader.py` | Lee el CSV del curso y arma los grupos. No guarda RUT ni correos. |
| `gitio.py` | Todo lo que llama a `git` y a `gh` por subproceso. Levanta `GitError`. |
| `runio.py` | Log de la corrida y lectura/escritura de los JSON. |
| `clone_repos.py` | Entrypoint: selección de grupos, clonado, checkout, manifiesto y resumen. |

## Decisiones tomadas, y por qué

- **La línea base del diff es el commit inicial del repositorio.** En un repo creado
  desde template ese commit es el código que recibió el grupo, así que el diff
  contra él es exactamente su trabajo. No hace falta red ni un remote `upstream`.
  `--base-ref` existe para cuando el equipo docente actualizó el base después.
- **El destino de los clones lo decide el operador** (`--dest`, o `[assessment]
  clones` en `course.toml`). Son gigabytes de código ajeno; no viven acá.
- **Las salidas se anidan por curso y por tarea.** Un curso corre esta herramienta
  varias veces al semestre: sin el nivel de la tarea, la revisión de la segunda
  pisaría a la de la primera. El nombre sale de `--tarea`, de `[assessment]
  assignment` o del literal de `repos.name_format` (`tarea-1-grupo-{n:02d}` da
  `tarea-1`), en ese orden. Vive en `config.assignment_slug()` y en
  `config.output_dir()`, y viaja a la skill dentro del manifiesto.
- **Con corte por fecha el checkout queda desprendido.** Ese commit rara vez es la
  punta de una rama, y crear una rama local que arriba no existe confunde al
  revisar.
- **El dry-run acá es `--dry-run`, no `--apply`.** La regla de `--apply` protege las
  escrituras en GitHub, y esta herramienta solo lee de GitHub. Lo que sí toca es el
  disco del operador, y de ahí las guardas: no pisa un clon con cambios locales sin
  `--force` y no clona sobre un directorio ocupado.

## Reglas heredadas

- Python 3.11+ y solo biblioteca estándar, salvo necesidad real y conversada. `git`
  y `gh` se invocan por subproceso.
- Nada específico de un curso en los `.py`: organización, nombres de repos, rutas y
  solución canónica van a `course.toml`, y toda clave nueva se documenta en
  `course.example.toml`.
- **Ninguna escritura contra GitHub sin confirmación explícita del usuario.** Hoy la
  herramienta solo lee. Si algún día publica comentarios o notas, vuelve a regir el
  `--apply` con confirmación interactiva de `assignment-preparation`.
- **Idempotencia**: volver a correr actualiza, no duplica. La skill no pisa un
  `QUESTIONS.md` ya escrito salvo que se lo pidan.
- **Aislamiento de fallos**: un grupo que falla no aborta a los siguientes; su error
  queda en el manifiesto y en el resumen final.
- El token se obtiene a través de `gh` en runtime; nunca se escribe a disco ni se
  pasa por la línea de comandos.
- Datos personales de alumnos (RUT, correos) fuera del código y de los logs. El
  roster trae correo y RUT: `roster_loader` los descarta al construir `Student`.

## Salidas y datos sensibles

Los clones traen el código de alumnos identificados y las minutas hablan de su
desempeño. Nada de eso se versiona: el `.gitignore` de la raíz excluye `clones/`,
`output/`, `logs/` y `state/`. Al agregar una salida nueva, comprueba que caiga
dentro de esos directorios o agrégala al `.gitignore`.

Las minutas son insumo del ayudante. No son una nota ni una acusación: describen
código y qué hay que saber para explicarlo. Si trabajas en la skill, mantén ese tono.

## Entradas compartidas

`course.toml` y el roster viven en la **raíz** del repositorio y los comparten las
dos herramientas: resuélvelos contra `REPO_ROOT` (`BASE_DIR.parent`), no contra el
directorio del módulo, y no los reescribas.

## Independencia

Este proyecto no importa módulos de `assignment-preparation`. `config.py`,
`roster_loader.py` y `runio.py` se parecen a los de allá y son distintos a propósito:
acá el roster no necesita fechas de creación y la configuración necesita rutas de
evaluación. Si algo se necesita idéntico en ambos, primero conversarlo.

El script de la skill (`scripts/contexto.py`) tampoco importa nada de acá: se comunica
con la herramienta por el manifiesto. Así se puede correr a mano desde cualquier
directorio del repositorio.
