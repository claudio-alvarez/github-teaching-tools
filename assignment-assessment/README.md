# Evaluación de trabajos de grupo

Herramienta de línea de comandos para **descargar** los repositorios que los grupos
entregaron, más una skill que **genera las preguntas de revisión de código** con las
que el ayudante interroga a cada grupo sobre lo que escribió.

Son dos piezas encadenadas:

| Pieza | Qué hace |
|---|---|
| `clone_repos.py` | Clona o actualiza un repositorio por grupo, según el roster, en el directorio que tú elijas. Deja un manifiesto `clones.json` con lo que encontró. |
| skill [`preguntas-revision`](../.claude/skills/preguntas-revision/) | Lee ese manifiesto y escribe `output/<SIGLA-CURSO>/<TAREA>/grupo-XX/QUESTIONS.md` con tres preguntas ancladas al código de cada grupo. |

Los repositorios son los que creó
[`assignment-preparation`](../assignment-preparation/), sobre la misma organización,
el mismo `course.toml` y el mismo roster.

## Requisitos

- Python 3.11 o superior (usa `tomllib` de la biblioteca estándar).
- `git` en el PATH.
- [GitHub CLI](https://cli.github.com/) (`gh`) autenticado con una cuenta con acceso
  a los repositorios del curso. Resuelve la autenticación de los repos privados; el
  token no se escribe a disco ni aparece en ninguna línea de comandos.

No hay dependencias que instalar.

## Descargar los repositorios

```bash
cd assignment-assessment
python3 clone_repos.py --dest ~/revision/tarea1
```

Recorre todos los grupos del roster y, para cada uno, clona el repositorio o
actualiza el clon que ya esté. Al terminar deja el manifiesto
`~/revision/tarea1/clones.json`.

**Tú decides dónde viven los clones.** Son el trabajo de todo el curso con su
historial completo, así que conviene un disco con espacio y fuera de este
repositorio. Si no pasas `--dest` se usa lo que declare `course.toml`:

```toml
[assessment]
clones = "clones/ICC3201-202620"   # relativo a assignment-assessment/
```

### Una tarea por corrida

El curso usa esta herramienta varias veces al semestre. Cada corrida queda marcada
con el nombre de la tarea que se está revisando, y ese nombre separa los
directorios de minutas:

```
output/ICC3201-202620/tarea-1/grupo-07/QUESTIONS.md
output/ICC3201-202620/tarea-2/grupo-07/QUESTIONS.md
```

El nombre se deduce del de los repositorios: con
`name_format = "tarea-1-grupo-{n:02d}"` sale `tarea-1`. Si tus repos no llevan la
tarea en el nombre, decláralo en `course.toml` (`[assessment] assignment`) o pásalo
en la corrida:

```bash
python3 clone_repos.py --dest ~/revision/tarea2 --tarea tarea-2
```

Dale a cada tarea su propio `--dest`: el manifiesto de un directorio describe una
tarea, y una corrida de otra tarea sobre el mismo destino lo reemplaza.

### Congelar la entrega en una fecha

```bash
python3 clone_repos.py --dest ~/revision/tarea1 --at 20/9/2026
```

Deja cada clon en el último commit anterior al cierre del 20 de septiembre y reporta
cuántos commits posteriores quedaron fuera. El checkout queda en HEAD desprendido,
porque ese estado no corresponde a la punta de ninguna rama. Con `--ref` puedes
revisar un tag o una rama distinta a la principal.

### Ejemplos

```bash
# Ver qué haría, sin tocar el disco
python3 clone_repos.py --dest ~/revision/tarea1 --dry-run

# Un par de grupos que llegaron tarde
python3 clone_repos.py --dest ~/revision/tarea1 --group 4 --group 9

# El tag de la entrega, en vez de la rama principal
python3 clone_repos.py --dest ~/revision/tarea1 --ref entrega-1

# Otro curso, con su propia configuración y su propio roster
python3 clone_repos.py --course ../course.ICC4203-202620.toml --dest ~/revision/t1-4203

# Trabajar sin red, con lo que ya está clonado
python3 clone_repos.py --dest ~/revision/tarea1 --no-fetch
```

### Opciones

| Flag | Efecto |
|---|---|
| `--dest RUTA` | Directorio de los clones. Por defecto, el de `course.toml`. |
| `--group N` | Solo ese grupo. Se puede repetir. Por defecto, todos. |
| `--ref REF` | Rama o tag a revisar. Por defecto, la rama principal del repo. |
| `--at D/M/AAAA` | Fecha de corte: último commit anterior a ese día. |
| `--tarea NOMBRE` | Nombre de la tarea; nombra el directorio de minutas. Por defecto, deducido del nombre de los repositorios. |
| `--base-ref REF` | Línea base del diff. Por defecto, el commit inicial del repositorio. |
| `--force` | Descarta los cambios locales del clon antes de actualizarlo. |
| `--no-fetch` | No consulta el remoto; usa lo que ya está en disco. |
| `--dry-run` | Muestra qué clonaría, sin escribir nada. |
| `--course RUTA` | Archivo de configuración del curso. Por defecto `course.toml`. |
| `--roster RUTA` | CSV del roster. Por defecto, el que declare el curso. |

Códigos de salida: `0` todo bien · `1` hubo grupos fallidos · `2` error de
configuración, de roster o de herramientas faltantes.

### Qué hace con un clon que ya existe

Volver a correrlo es la operación normal: no vuelve a clonar nada, hace `fetch` y
mueve el checkout al commit que corresponda. Antes comprueba dos cosas:

- Que el clon apunte al repositorio esperado de la organización. Si el directorio
  quedó con otro repo adentro, se detiene en ese grupo y sigue con el resto.
- Que no tenga cambios sin commitear en archivos versionados. Si alguien anotó algo
  en el clon, lo deja intacto y lo reporta; con `--force` descarta esos cambios y lo
  actualiza. Lo que no está versionado (un `__pycache__`, un `target/` que quedó de
  ejecutar el código) no bloquea nada: el checkout no lo toca.

Un grupo que falle no detiene a los siguientes.

### La línea base del diff

Para saber qué escribió el grupo hace falta saber qué recibió. En un repositorio
creado desde un template, el **commit inicial es exactamente el código base**:
GitHub aplasta el template en un solo commit. Esa es la línea base por defecto y no
necesita red ni remotes adicionales.

Si el equipo docente publicó actualizaciones al código base después de crear los
repositorios, pásale la referencia correcta con `--base-ref` (por ejemplo,
`upstream/main` en los clones que tengan ese remote configurado).

## Generar las minutas de revisión

Con los repositorios descargados, desde Claude Code:

```
/preguntas-revision
```

Para cada grupo lee el enunciado de la tarea (el `README.md` de la raíz del
repositorio), estudia el diff contra el código base, elige de una a tres regiones
con lógica relevante y escribe tres preguntas: explicación de nivel algorítmico y
simulación de una ejecución concreta. Los grupos sin avance suficiente reciben
preguntas sobre la **solución canónica** del equipo docente. Cada fragmento citado
lleva encima su archivo y rango de líneas, para que el ayudante pueda abrirlo
mientras pregunta.

La documentación completa de la skill, con todos sus argumentos, está en
[`.claude/skills/preguntas-revision/README.md`](../.claude/skills/preguntas-revision/README.md).

## Qué queda en disco

```
~/revision/tarea1/              # donde tú elijas
├── clones.json                 # manifiesto: qué grupo, qué commit, cuánto avance
├── grupo-01/
└── grupo-02/

assignment-assessment/
├── logs/                       # una bitácora por corrida
├── state/clones.json           # dónde quedó la última descarga
└── output/ICC3201-202620/
    └── tarea-1/
        └── grupo-01/QUESTIONS.md   # la minuta de revisión
```

Nada de eso se versiona: los clones traen código de alumnos y las minutas hablan de
personas identificadas. El `.gitignore` de la raíz ya excluye `clones/`, `output/`,
`logs/` y `state/`.

El manifiesto `clones.json` es la interfaz entre las dos piezas. Por cada grupo
guarda el repositorio, la ruta del clon, los integrantes, el ayudante, la rama y el
commit revisados, el commit base, cuántos commits hay sobre él, el tamaño del diff y
el reparto de commits por autor. En la cabecera van el curso, la tarea y el
directorio de minutas que le corresponde. Una corrida con `--group` actualiza solo a esos
grupos y conserva a los demás.

## Configuración del curso

`course.toml` y el roster viven **en la raíz del repositorio** porque los comparten
las dos herramientas. Esta lee de ahí la organización, la convención de nombres de
los repositorios y el CSV del curso; no reescribe ninguno de los dos.

Lo propio de la evaluación va en la sección `[assessment]`, toda opcional y
documentada en [`course.example.toml`](../course.example.toml):

```toml
[course]
slug = "ICC3201-202620"          # nombra el directorio de salida

[assessment]
clones = "clones/ICC3201-202620"
output = "output"
assignment = "tarea-1"           # nombra el directorio de la tarea
canonical_repo = "~/cursos/icc3201/solucion-t1"
canonical_branch = "solucion"
canonical_base = "main"
```

## Problemas frecuentes

**«falta(n) en el PATH: gh»** — instala GitHub CLI y corre `gh auth login`. Sin él
no se pueden clonar repositorios privados.

**Un grupo falla con 404** — el repositorio no existe todavía (créalo con
`assignment-preparation`) o tu cuenta no tiene acceso a la organización.

**«ya existe, no está vacío y no es un repositorio git»** — hay un directorio con el
nombre del repo ocupado por otra cosa en el destino. Muévelo o usa otro `--dest`.

**«el clon existente apunta a otro repo»** — el destino se usó antes para otro curso.
Dale a cada curso su propio `--dest`.

**«el clon tiene cambios locales»** — alguien editó los archivos del clon. Revisa con
`git -C <clon> status` y, si no hay nada que rescatar, corre con `--force`.

**Un grupo aparece sin avance y sabes que entregó** — puede que haya trabajado en
otra rama. Revisa con `git -C <clon> branch -a` y vuelve a correr con
`--ref <rama> --group N`.
