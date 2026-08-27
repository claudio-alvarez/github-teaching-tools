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
└── assignment-assessment/    # evaluación de los trabajos entregados
```

| Directorio | Qué hace |
|---|---|
| [`assignment-preparation/`](assignment-preparation/) | Crea y configura los repositorios de los grupos a partir de un template y de la planilla del curso: invita a los integrantes, da acceso al team docente y abre el issue de bienvenida. |
| [`assignment-assessment/`](assignment-assessment/) | Evaluación de los trabajos entregados en esos repositorios. En etapa inicial. |

Cada herramienta se ejecuta a mano, desde su propio directorio. No hay servicios ni
cron.

## Puesta en marcha

```bash
cp course.example.toml course.toml   # y edítalo con los datos de tu curso
```

Deja tu planilla de alumnos en `roster/roster.csv`; el formato está en
[`roster/roster_example.csv`](roster/roster_example.csv). Después, ve al README de la
herramienta que quieras usar.

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
