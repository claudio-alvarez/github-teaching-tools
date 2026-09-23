# github-teaching-tools

Herramientas de línea de comandos para administrar los trabajos de un curso sobre
GitHub. Cada herramienta es un proyecto independiente, pero todas leen la **misma
configuración de curso y el mismo roster**, que viven en la raíz.

```
github-teaching-tools/
├── course.toml               # curso activo (no se versiona)
├── course.example.toml       # plantilla documentada
├── roster/roster.csv         # planilla de alumnos (no se versiona)
├── assignment-preparation/   # creación de los repositorios de grupo
├── assignment-assessment/    # descarga y evaluación de los trabajos entregados
├── assignment-mailings/      # correos personalizados a los estudiantes (mailmerge)
└── .claude/skills/           # skills de Claude Code propias del repositorio
```

| Directorio | Qué hace |
|---|---|
| [`assignment-preparation/`](assignment-preparation/) | Crea y configura los repositorios de los grupos a partir de un template y de la planilla del curso: invita a los integrantes, da acceso al team docente y abre el issue de bienvenida. También reenvía las invitaciones que caducaron. |
| [`assignment-assessment/`](assignment-assessment/) | Descarga los repositorios de los grupos para revisarlos localmente, con la opción de congelar la entrega en una fecha de corte. Con la skill [`preguntas-revision`](.claude/skills/preguntas-revision/) genera, por grupo, tres problemas candidatos de revisión de código; con [`preparar-iet`](.claude/skills/preparar-iet/) convierte el problema que marque el docente en el enunciado y la pauta del ítem de evaluación de tarea, en markdown y PDF; con [`preparar-impresion-iet`](.claude/skills/preparar-impresion-iet/) arma el PDF único para imprimir, validado contra el roster. |
| [`assignment-mailings/`](assignment-mailings/) | Envía correos personalizados a los estudiantes con `mailmerge` desde la cuenta corporativa del docente: repositorio asignado, credenciales, recordatorios. Arma la base de datos desde el roster; las plantillas se versionan y los datos no. |

Cada herramienta se ejecuta a mano, desde su propio directorio. No hay servicios ni
cron.

## Puesta en marcha

```bash
cp course.example.toml course.toml   # y edítalo con los datos de tu curso
```

Deja tu planilla de alumnos en `roster/roster.csv`; el formato está en
[`roster/roster_example.csv`](roster/roster_example.csv). Después, ve al README de la
herramienta que quieras usar.

**Con más de un curso activo, cada uno necesita su propio CSV**: los alumnos son
distintos. Deja los archivos en `roster/` y apunta cada `course*.toml` al suyo con
la clave `roster` de `[course]`. Las herramientas se niegan a invitar cuando el
roster no corresponde a la organización del curso, pero es mejor no llegar ahí.

## Convenciones del repositorio

- **Python 3.11+ y solo biblioteca estándar**, salvo necesidad real y conversada.
- **Nada específico de un curso en el código.** La organización, el template, el
  team docente y los textos van en `course.toml`, no en los `.py`.
- **Entradas compartidas, salidas propias.** `course.toml` y `roster/` son de todo el
  repositorio; los logs y el estado de cada corrida quedan dentro del directorio de
  la herramienta que los generó.
- **Datos de alumnos fuera del control de versiones.** El `.gitignore` de la raíz
  excluye `**/roster/*.csv` y `course*.toml`; se versionan solo los ejemplos
  (`roster_example.csv`, `course.example.toml`). Los RUT, correos y tokens no se
  suben a ningún remoto.
- Cada proyecto trae su propio `README.md` (uso) y `AGENTS.md` (guía para agentes).
- **Las skills del repositorio viven en `.claude/skills/`** y cada una documenta su
  invocación en un `README.md` propio. Las partes deterministas van en un script de
  la skill, para poder correrlas y revisarlas a mano.
