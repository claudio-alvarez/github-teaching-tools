# AGENTS.md — Evaluación de trabajos de grupo

Guía para agentes que trabajen en `assignment-assessment/`. Ver también el
[`AGENTS.md` de la raíz](../AGENTS.md) y, para el contexto de cómo se crearon los
repositorios que acá se evalúan,
[`assignment-preparation/AGENTS.md`](../assignment-preparation/AGENTS.md).

## Estado

El proyecto está **sin implementar**. El [README](README.md) lista las decisiones
de diseño pendientes. **No escribir código hasta que el usuario las resuelva**: no
inventar una rúbrica, un formato de informe ni un esquema de datos por tu cuenta.

## Reglas heredadas

Aunque el código sea nuevo, valen los mismos invariantes que en
`assignment-preparation`:

- Python 3.11+ y solo biblioteca estándar, salvo necesidad real y conversada.
- Nada específico de un curso en los `.py`: organización, repos, fechas, pesos de la
  rúbrica y textos van a configuración.
- **Dry-run por defecto** y confirmación explícita antes de cualquier escritura
  contra GitHub. Publicar comentarios o notas es visible para los estudiantes.
- **Idempotencia**: volver a correr no debe duplicar comentarios ni informes.
- **Aislamiento de fallos**: un grupo que falla no aborta a los siguientes.
- El token se obtiene con `gh auth token` en runtime; nunca se escribe a disco.
- Datos personales de alumnos (RUT, correos) y notas no se versionan.

## Entradas compartidas

`course.toml` y `roster/roster.csv` viven en la **raíz** del repositorio y los
comparten las dos herramientas: resuélvelos contra `BASE_DIR.parent`, no contra el
directorio del módulo, y no los reescribas. Las salidas propias (logs, informes,
estado) van dentro de `assignment-assessment/` y no se versionan.

Configuración nueva de evaluación va a una sección propia de `course.toml`,
documentada en `course.example.toml`.

## Independencia

Este proyecto no importa módulos de `assignment-preparation`. Si algo se necesita en
ambos, primero conversarlo: duplicar unas líneas es preferible a crear un paquete
compartido sin acuerdo.
