# Skill `preguntas-revision`

Genera, para cada grupo del curso, una minuta con **tres problemas candidatos de
revisión de código**, anclados a fragmentos concretos de lo que el grupo entregó.
Cada problema vale **10 puntos** repartidos en sub-partes según un **schema**. El
docente marca uno de los tres en el archivo, y ese pasa a la etapa siguiente, donde
se formatea como enunciado para los estudiantes.

La skill la ejecuta Claude Code dentro de este repositorio. Lo que tú haces es
descargar los repositorios, invocarla y después marcar un problema por grupo.

```
github-teaching-tools/
├── .claude/skills/preguntas-revision/     ← esta skill
│   ├── SKILL.md                           ← instrucciones que sigue el agente
│   ├── README.md                          ← este archivo
│   ├── schemas/<slug>.md                  ← schemas de sub-partes y puntaje
│   └── scripts/contexto.py                ← extractor de contexto (stdlib + git)
└── assignment-assessment/
    ├── clone_repos.py                     ← descarga los repos (paso previo)
    └── output/<SIGLA-CURSO>/<TAREA>/grupo-XX/QUESTIONS.md   ← lo que produce la skill
```

## Requisito previo: descargar los repositorios

La skill **no clona nada**. Trabaja sobre los clones que deja `clone_repos.py` y
sobre el manifiesto `clones.json` que ese comando escribe en el directorio de
destino:

```bash
cd assignment-assessment
python3 clone_repos.py --dest ~/revision/tarea1
```

Ver [`assignment-assessment/README.md`](../../../assignment-assessment/README.md)
para las opciones de descarga (fecha de corte, subconjunto de grupos, etc.).

## Cómo se invoca

Desde Claude Code, parado en cualquier directorio del repositorio:

```
/preguntas-revision
```

Sin argumentos procesa **todos los grupos de la última descarga** con el schema
`default` y salta los que ya tengan su `QUESTIONS.md`. También funciona pidiéndolo
en lenguaje natural («genera los problemas de revisión de los grupos», «prepara la
minuta del grupo 7», «los primeros cinco grupos para probar»): la skill se activa
sola.

### Argumentos

| Argumento | Para qué |
|---|---|
| `--clones DIR` | Directorio de clones distinto al de la última descarga. |
| `--group N` | Solo ese grupo. Se puede repetir: `--group 4 --group 9`. |
| `--schema SLUG` | Schema de sub-partes y puntaje (ver más abajo). Por defecto, `default`. |
| `--canonica RUTA --rama RAMA` | Repositorio local y rama con la solución canónica, para los grupos sin avance. |
| `--base REF` | Rama o commit del código base dentro del repo canónico. Por defecto, su commit inicial. |
| `--tarea NOMBRE` | Nombre de la tarea, que da nombre a su directorio de minutas. Por defecto, el de la descarga. |
| `--rehacer` | Regenera las minutas que ya existen (por defecto se saltan). |
| `--output DIR` | Escribe las minutas en otro directorio raíz. |

### Ejemplos

```
/preguntas-revision
/preguntas-revision --group 7
/preguntas-revision --group 4 --group 9 --rehacer
/preguntas-revision --schema default --group 1 --group 2 --group 3
/preguntas-revision --clones ~/revision/tarea1
/preguntas-revision --tarea tarea-2
/preguntas-revision --canonica ~/cursos/icc3201/solucion-t1 --rama solucion
/preguntas-revision --canonica ~/cursos/icc3201/base --rama solucion --base main
```

Si `course.toml` declara la solución canónica en `[assessment]`, no hace falta
pasarla: viene en el manifiesto.

```toml
[assessment]
canonical_repo = "~/cursos/icc3201/solucion-t1"
canonical_branch = "solucion"
canonical_base = "main"            # opcional
```

## Qué hace, paso a paso

1. Carga y valida el **schema** (`schemas/<slug>.md`): cuántas sub-partes tiene cada
   problema, qué mide cada una y cuántos puntos vale.
2. Lee `clones.json` y lista los grupos: estado del clon, commits sobre el código
   base, tamaño del diff, si ya tienen minuta y si el docente ya marcó un problema.
3. Para cada grupo pendiente, obtiene el **enunciado** (el `README.md` de la raíz
   del repositorio clonado, que es el que entregó el equipo docente) y el **diff
   contra el código base** (el commit inicial del repositorio, que en un repo
   creado desde template es exactamente el código entregado).
4. Busca en ese diff las regiones con lógica que resuelve los objetivos del
   enunciado, descartando configuración, código generado y andamiaje, y elige
   **tres secciones**, una por problema, lo más distintas posible entre sí.
5. Escribe los **tres problemas candidatos**, cada uno con las sub-partes y los
   puntos del schema, autocontenido: cita el fragmento con su
   `archivo:desde-hasta`, cita textualmente los requisitos del enunciado a los que
   alude, y aporta lo que necesite del código base (constantes, firmas). Verifica
   los rangos de líneas contra el commit revisado y las simulaciones antes de
   escribir la respuesta esperada.
6. Escribe `output/<SIGLA-CURSO>/<TAREA>/grupo-XX/QUESTIONS.md`.

### Por qué los problemas son autocontenidos

En la etapa siguiente, el problema marcado se convierte en un enunciado que el
estudiante responde **sin el enunciado de la tarea y sin acceso al código de su
repositorio**. Por eso cada problema trae dentro todo lo que hace falta para
contestarlo: el fragmento, la cita textual de cualquier requisito que mencione, y
las definiciones del código base de las que dependa. Y como solo uno de los tres se
usa, ningún problema se apoya en otro. Esta regla vale para todos los schemas.

### El fallback de la solución canónica

Un grupo sin avance suficiente —repositorio intacto, solo `README` tocado, cambios
cosméticos— no da material para preguntar. En ese caso la skill toma los fragmentos
medulares de la **solución canónica** y formula los problemas sobre ellos, con el
mismo schema y el mismo criterio. La minuta lo dice arriba, de modo que el ayudante
sepa que está preguntando sobre código de referencia y no sobre el del grupo.

El umbral automático es de 30 líneas de código nuevas (o dos archivos con al menos
15), pero es solo una primera criba: la decisión final la toma la skill leyendo el
diff, porque 200 líneas copiadas no son avance y 25 líneas con el núcleo del
algoritmo sí lo son.

Si no hay solución canónica configurada ni pasada como argumento, la skill escribe
la minuta con el contexto del grupo, deja anotado que falta y te lo informa al
final. No inventa código.

## Schemas

Un schema define **cómo se estructura cada problema**: cuántas sub-partes tiene, qué
mide cada una, cuántos puntos vale y qué respuesta vale el puntaje completo o
parcial. Es un archivo markdown en `schemas/<slug>.md`, donde el nombre del archivo,
en kebab-case, **es** el slug con el que se pide (`--schema <slug>`).

### `default`

Tres sub-partes graduadas por dificultad sobre un mismo fragmento, 10 puntos:

| Parte | Puntos | Tipo | Qué mide |
|---|---|---|---|
| a | 4 | comprensión conceptual | Describir qué hace el código y por qué está construido así. |
| b | 3 | simulación de ejecución | Seguir el código con una entrada o estado inicial concreto. |
| c | 3 | detalle del código | Justificar una decisión puntual: una llamada, sus argumentos, su orden, qué pasaría si se cambiara. |

### `icc3201-tarea1-202620`

Hereda de `default` y cambia la progresión solo para los problemas sobre el
planificador MLFQ de la Tarea 1: (a) comprensión de la política pedida (ticks
frente a quantum, transiciones de nivel, bloqueo con quantum parcialmente consumido),
4 puntos; (b) explicación del código del grupo, 3; (c) simulación, 3. Los problemas
de la Parte 1 (`getprocs`, `ps`) siguen `default`. Razón: entender cómo actúan las
reglas del planificador discrimina mejor que cualquier detalle de implementación
entre quien delegó la tarea completa a un LLM y quien la trabajó a conciencia.

### Crear un schema propio

1. Copia `schemas/default.md` a `schemas/<mi-slug>.md`.
2. En el frontmatter pon `slug: <mi-slug>` (igual al nombre del archivo), un
   `nombre` legible y el total de `puntos`.
3. Deja una tabla con las columnas `Parte`, `Puntos` y `Tipo` (una fila por
   sub-parte; los puntos tienen que sumar el total). Es la única parte del archivo
   que el script interpreta, junto con el frontmatter.
4. Si el schema es una variante de otro, declara `hereda: <slug>` en el frontmatter y
   escribe solo lo que cambia; `contexto.py schema --slug` imprime el schema y, a
   continuación, el heredado, para que el agente lea ambos.
5. Escribe, para cada sub-parte, qué debe pedir y qué respuesta vale el puntaje
   completo, la mitad y cero. Eso es lo que sigue el agente.
6. Valida: `python3 .claude/skills/preguntas-revision/scripts/contexto.py schema --slug <mi-slug>`.

La regla de autocontención (citar fragmentos, requisitos y definiciones del código
base dentro del problema) no es del schema: la skill la aplica siempre.

## Qué produce

`assignment-assessment/output/<SIGLA-CURSO>/<TAREA>/grupo-XX/QUESTIONS.md`, con:

- **Encabezado**: curso, tarea, repositorio, commit revisado, integrantes, ayudante,
  tamaño del avance y schema usado con su reparto de puntos.
- **Selección para la evaluación**: una lista con los tres problemas y una casilla
  `[ ]` cada uno. Aquí marcas con `[x]` el que pasa a la etapa siguiente. Solo uno.
- **Qué pedía el enunciado**: dos o tres líneas de orientación para el revisor.
- **Problemas candidatos**: los tres problemas, cada uno con su fragmento citado
  dentro de la función que lo contiene (firma, `// ...` por lo omitido, llave de
  cierre) y, pegada encima, la referencia `archivo:desde-hasta` y el commit del que
  salió; las citas textuales del enunciado que necesite; y sus sub-partes con tipo
  y puntaje.
- **Para el revisor**: por problema y por sub-parte, la respuesta esperada, qué vale
  el puntaje completo y el parcial, y las señales de que el grupo no entiende ese
  código. Esta sección no se le muestra al grupo.

Cada tarea tiene su propio directorio, de modo que la revisión de la tarea 2 no
pisa la de la tarea 1. El nombre sale del manifiesto de la descarga (`--tarea` de
`clone_repos.py`, o deducido del nombre de los repositorios) y se puede sobrescribir
al invocar la skill.

Las minutas **no se versionan**: hablan del trabajo de alumnos identificados. El
`.gitignore` de la raíz ya excluye `output/`.

## Después de generar: marcar un problema

Abre el `QUESTIONS.md` de cada grupo, lee los tres candidatos y marca uno en la
sección «Selección para la evaluación»:

```markdown
- [ ] Problema 1 — Round-robin en nivel 1
- [x] Problema 2 — Copia segura al espacio de usuario
- [ ] Problema 3 — La guarda contra el desborde
```

`contexto.py listar` muestra en la última columna qué grupos ya tienen su problema
marcado (`P2 marcado`), cuáles no (`sin marcar`) y si alguno tiene más de uno
marcado por error.

Con las marcas puestas, la skill [`preparar-iet`](../preparar-iet/) convierte el
problema elegido de cada grupo en `STATEMENT.md` (enunciado para los estudiantes),
`SOLUTION.md` (pauta para los ayudantes) y sus PDF.

## El script de contexto

`scripts/contexto.py` es la parte determinista: la usa la skill, pero también puedes
correrla tú para ver qué está mirando el agente. Solo biblioteca estándar y `git`.

```bash
# Desde la raíz del repositorio
python3 .claude/skills/preguntas-revision/scripts/contexto.py schema --listar
python3 .claude/skills/preguntas-revision/scripts/contexto.py schema --slug default
python3 .claude/skills/preguntas-revision/scripts/contexto.py listar
python3 .claude/skills/preguntas-revision/scripts/contexto.py grupo --group 7
python3 .claude/skills/preguntas-revision/scripts/contexto.py grupo --group 7 --solo-resumen
python3 .claude/skills/preguntas-revision/scripts/contexto.py canonica \
    --repo ~/cursos/icc3201/solucion-t1 --branch solucion --base main
python3 .claude/skills/preguntas-revision/scripts/contexto.py archivo \
    --group 7 --ruta src/router.py --desde 11 --hasta 19
```

| Subcomando | Qué imprime |
|---|---|
| `schema` | Valida un schema (`--slug`) y lo imprime entero, o lista los disponibles con su reparto de puntos (`--listar`). |
| `listar` | Tabla de todos los grupos del manifiesto: estado, commits, tamaño del diff, veredicto de avance y si ya existe la minuta y tiene un problema marcado. |
| `grupo --group N` | Digesto de un grupo: integrantes, commit revisado, ruta del enunciado, archivos tocados, veredicto y diff contra el base. |
| `canonica` | Lo mismo para la solución canónica: archivos y diff de la rama de solución contra el base. |
| `archivo --ruta X` | Imprime un archivo con números de línea, leído del commit revisado, y la referencia lista para citar. Acepta `--group N` o `--repo RUTA --branch RAMA`, y se acota con `--desde`/`--hasta`. Con `--marco` imprime el rango dentro de su función: firma arriba, `// ...` por lo omitido y llave de cierre, listo para pegar. |

Opciones útiles: `--clones DIR` (otro directorio de clones), `--min-lineas N`
(umbral del veredicto), `--max-lineas`/`--max-total` (cuánto diff imprimir),
`--solo-resumen` (sin diff).

## Problemas frecuentes

**«No existe clones.json»** — todavía no has descargado los repositorios, o el
`--clones` apunta a otro directorio. Corre `clone_repos.py --dest RUTA` primero.

**«Schema … inválido»** — el `slug` del frontmatter no coincide con el nombre del
archivo, falta `puntos`, o las filas de la tabla no suman el total. El mensaje dice
cuál de las tres.

**Un grupo aparece como `error` o `sin clon`** — la descarga de ese repositorio
falló (repositorio inexistente, sin permisos, directorio ocupado). Revisa el log de
`assignment-assessment/logs/` y vuelve a correr `clone_repos.py --group N`.

**Un grupo aparece como `con_cambios_locales`** — alguien editó el clon. Los
problemas se generan igual, sobre lo que hay en disco; si quieres el estado limpio
del remoto, corre `clone_repos.py --group N --force`.

**Los problemas salen genéricos** — casi siempre es que el diff venía truncado o
que el repositorio no trae enunciado en la raíz. Sube `--max-total`, o dile a la
skill sobre qué archivos quieres que se concentre.

**Las minutas no se regeneran** — es el comportamiento por defecto: no se pisa una
minuta ya escrita (y con ella, la marca del docente). Usa `--rehacer`.

**`listar` dice «2 marcados (!)»** — hay más de una casilla `[x]` en esa minuta.
Deja una sola antes de la etapa siguiente.
