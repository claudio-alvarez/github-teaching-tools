# Skill `preguntas-revision`

Genera, para cada grupo del curso, una minuta con **tres preguntas de revisión de
código** ancladas a fragmentos concretos de lo que el grupo entregó. Es lo que el
ayudante lleva impreso a la revisión presencial.

La skill la ejecuta Claude Code dentro de este repositorio. Lo que tú haces es
descargar los repositorios y después invocarla.

```
github-teaching-tools/
├── .claude/skills/preguntas-revision/     ← esta skill
│   ├── SKILL.md                           ← instrucciones que sigue el agente
│   ├── README.md                          ← este archivo
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

Sin argumentos procesa **todos los grupos de la última descarga** y salta los que
ya tengan su `QUESTIONS.md`. También funciona pidiéndolo en lenguaje natural
(«genera las preguntas de revisión de los grupos» o «prepara la minuta del grupo
7»): la skill se activa sola.

### Argumentos

| Argumento | Para qué |
|---|---|
| `--clones DIR` | Directorio de clones distinto al de la última descarga. |
| `--group N` | Solo ese grupo. Se puede repetir: `--group 4 --group 9`. |
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

1. Lee `clones.json` y lista los grupos: estado del clon, commits sobre el código
   base, tamaño del diff y si ya tienen minuta.
2. Para cada grupo pendiente, obtiene el **enunciado** (el `README.md` de la raíz
   del repositorio clonado, que es el que entregó el equipo docente) y el **diff
   contra el código base** (el commit inicial del repositorio, que en un repo
   creado desde template es exactamente el código entregado).
3. Busca en ese diff las regiones con lógica que resuelve los objetivos del
   enunciado, descartando configuración, código generado y andamiaje.
4. Elige de una a tres secciones y escribe **tres preguntas** repartidas entre
   ellas, de dos tipos: explicación de nivel algorítmico y simulación de una
   ejecución concreta. Siempre hay al menos una de cada tipo.
5. Escribe `output/<SIGLA-CURSO>/<TAREA>/grupo-XX/QUESTIONS.md`, con cada
   fragmento citado precedido de su `archivo:desde-hasta`.

### El fallback de la solución canónica

Un grupo sin avance suficiente —repositorio intacto, solo `README` tocado, cambios
cosméticos— no da material para preguntar. En ese caso la skill toma los fragmentos
medulares de la **solución canónica** y formula las preguntas sobre ellos, con el
mismo criterio. La minuta lo dice arriba, de modo que el ayudante sepa que está
preguntando sobre código de referencia y no sobre el del grupo.

El umbral automático es de 30 líneas de código nuevas (o dos archivos con al menos
15), pero es solo una primera criba: la decisión final la toma la skill leyendo el
diff, porque 200 líneas copiadas no son avance y 25 líneas con el núcleo del
algoritmo sí lo son.

Si no hay solución canónica configurada ni pasada como argumento, la skill escribe
la minuta con el contexto del grupo, deja anotado que falta y te lo informa al
final. No inventa código.

## Qué produce

`assignment-assessment/output/<SIGLA-CURSO>/<TAREA>/grupo-XX/QUESTIONS.md`, con:

- **Encabezado**: curso, tarea, repositorio, commit revisado, integrantes, ayudante
  y tamaño del avance.
- **Qué pedía el enunciado**: los objetivos que tocan las preguntas.
- **Tres preguntas**, cada una con su fragmento citado y, pegada encima, la
  referencia `archivo:desde-hasta` y el commit del que salió. Así el ayudante abre
  el archivo en esa línea mientras pregunta, y el fragmento sigue siendo ubicable
  cuando el grupo siga trabajando sobre el repositorio.
- **Para el revisor**: la respuesta esperada de cada pregunta y las señales de que
  el grupo no entiende ese código. Esta sección no se le muestra al grupo.

Cada tarea tiene su propio directorio, de modo que la revisión de la tarea 2 no
pisa la de la tarea 1. El nombre sale del manifiesto de la descarga (`--tarea` de
`clone_repos.py`, o deducido del nombre de los repositorios) y se puede sobrescribir
al invocar la skill.

Las minutas **no se versionan**: hablan del trabajo de alumnos identificados. El
`.gitignore` de la raíz ya excluye `output/`.

## El script de contexto

`scripts/contexto.py` es la parte determinista: la usa la skill, pero también puedes
correrla tú para ver qué está mirando el agente. Solo biblioteca estándar y `git`.

```bash
# Desde la raíz del repositorio
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
| `listar` | Tabla de todos los grupos del manifiesto: estado, commits, tamaño del diff, veredicto de avance y si ya existe la minuta. |
| `grupo --group N` | Digesto de un grupo: integrantes, commit revisado, ruta del enunciado, archivos tocados, veredicto y diff contra el base. |
| `canonica` | Lo mismo para la solución canónica: archivos y diff de la rama de solución contra el base. |
| `archivo --ruta X` | Imprime un archivo con números de línea, leído del commit revisado, y la referencia lista para citar. Acepta `--group N` o `--repo RUTA --branch RAMA`, y se acota con `--desde`/`--hasta`. |

Opciones útiles: `--clones DIR` (otro directorio de clones), `--min-lineas N`
(umbral del veredicto), `--max-lineas`/`--max-total` (cuánto diff imprimir),
`--solo-resumen` (sin diff).

## Problemas frecuentes

**«No existe clones.json»** — todavía no has descargado los repositorios, o el
`--clones` apunta a otro directorio. Corre `clone_repos.py --dest RUTA` primero.

**Un grupo aparece como `error` o `sin clon`** — la descarga de ese repositorio
falló (repositorio inexistente, sin permisos, directorio ocupado). Revisa el log de
`assignment-assessment/logs/` y vuelve a correr `clone_repos.py --group N`.

**Un grupo aparece como `con_cambios_locales`** — alguien editó el clon. Las
preguntas se generan igual, sobre lo que hay en disco; si quieres el estado limpio
del remoto, corre `clone_repos.py --group N --force`.

**Las preguntas salen genéricas** — casi siempre es que el diff venía truncado o
que el repositorio no trae enunciado en la raíz. Sube `--max-total`, o dile a la
skill sobre qué archivos quieres que se concentre.

**Las minutas no se regeneran** — es el comportamiento por defecto: no se pisa una
minuta ya escrita. Usa `--rehacer`.
