# Evaluación de trabajos de grupo

Proyecto **en etapa inicial**: por ahora solo están el propósito y las decisiones
que faltan por tomar. Todavía no hay código.

## Propósito

Apoyar la evaluación de los trabajos que los grupos entregan en los repositorios
creados por [`assignment-preparation`](../assignment-preparation/), sobre la misma
organización de GitHub y la misma planilla del curso.

## Punto de partida

Las entradas ya existen y son **compartidas**, en la raíz del repositorio:

- [`course.toml`](../course.example.toml) — organización, template, team docente y
  convención de nombres de los repos. Única fuente de configuración del curso.
- [`roster/roster.csv`](../roster/roster_example.csv) — alumnos, grupos y fechas.

Esta herramienta las lee igual que `assignment-preparation`; no las reescribe. Si la
evaluación necesita configuración propia (rúbrica, pesos, fecha de corte), va a una
sección nueva de `course.toml`, documentada en `course.example.toml`.

Del proyecto vecino conviene reutilizar el **modelo**, no el código: un cliente HTTP
sobre `urllib` con el token de `gh auth token`, dry-run por defecto y confirmación
explícita antes de escribir.

## Por definir

- **Qué se evalúa**: ¿la entrega en la rama principal a una fecha de corte, un tag,
  un release, un pull request?
- **Qué produce la herramienta**: ¿un informe por grupo, una planilla de notas,
  comentarios publicados en el repositorio de cada grupo?
- **Qué se recolecta de GitHub**: commits por integrante, PRs, issues, revisiones,
  fecha de la última entrega.
- **Qué queda a criterio del docente** y qué se automatiza.
- **Rúbrica**: dónde vive y en qué formato.

Hasta que eso esté decidido, no agregar código especulativo.
