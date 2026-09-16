# AGENTS.md — github-teaching-tools

Repositorio con dos proyectos independientes que comparten los datos del curso.
**Antes de trabajar en uno, lee su `AGENTS.md` propio**, que es la guía que manda
dentro de ese directorio:

- [`assignment-preparation/AGENTS.md`](assignment-preparation/AGENTS.md) — creación
  y configuración de los repositorios de grupo.
- [`assignment-assessment/AGENTS.md`](assignment-assessment/AGENTS.md) — descarga
  y evaluación de los trabajos entregados, y la skill que genera las preguntas de
  revisión.

## Qué es compartido y qué no

En la raíz viven las **entradas comunes**: `course.toml` (con su plantilla
`course.example.toml`) y `roster/roster.csv` (con `roster_example.csv`). Las dos
herramientas las leen; ninguna las reescribe.

Las **salidas** de cada corrida (`logs/`, `state/`) quedan dentro del directorio de
la herramienta que las generó, nunca en la raíz.

El **código no se comparte**: `assignment-assessment` no importa módulos de
`assignment-preparation` ni al revés. Si algo hace falta en ambos, conversarlo antes
de crear un paquete común; duplicar unas líneas es preferible a un acoplamiento no
acordado.

Al agregar una ruta, decide si es entrada compartida (va a la raíz, resuelta contra
`REPO_ROOT`) o salida propia (va al directorio de la herramienta, contra `BASE_DIR`).

## Skills

Las skills de Claude Code propias del repositorio viven en `.claude/skills/<nombre>/`
y son parte del producto, con el mismo estándar que el código:

- `SKILL.md` con el procedimiento que sigue el agente y `README.md` con la
  documentación de invocación para el usuario.
- Lo determinista va en un script de `scripts/`, en Python 3.11+ de biblioteca
  estándar, ejecutable a mano para poder revisar qué está mirando el agente.
- Una skill no importa módulos de las herramientas: se comunica con ellas por los
  archivos que estas producen.

## Reglas de todo el repositorio

- Python 3.11+ y solo biblioteca estándar, salvo necesidad real y conversada.
- Nada específico de un curso hardcodeado en los `.py`: va a `course.toml`.
- Toda clave nueva de `course.toml` se documenta también en `course.example.toml`.
- Datos personales de alumnos (RUT, correos) y tokens **nunca** se versionan ni se
  loguean más allá de lo mínimo para identificar un problema. El `.gitignore` de la
  raíz excluye `**/roster/*.csv` y `course*.toml`, con excepción de los ejemplos.
- Ninguna operación de escritura contra GitHub sin confirmación explícita del
  usuario en la conversación.
