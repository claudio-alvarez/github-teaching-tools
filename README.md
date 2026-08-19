# Creación de repositorios de grupo para cursos

Herramienta de línea de comandos para crear y configurar, de una vez, los
repositorios de GitHub de los grupos de un curso.

A partir de una planilla con los alumnos y sus grupos, para cada grupo:

1. Crea un repositorio en la organización del curso a partir de un **repositorio
   template**.
2. Invita a los integrantes del grupo como colaboradores.
3. Le da acceso al **team docente** (ayudantes).
4. Abre un **issue de bienvenida** con las instrucciones para configurar el
   repositorio base como `upstream` en sus clones locales.

Los grupos se procesan **según la fecha de creación indicada en la planilla**, de
modo que puedes ejecutar la herramienta el día que corresponda y solo se crearán
los repositorios de ese día.

No es un servicio ni un cron: lo ejecutas tú a mano cuando toca.

## Requisitos

- Python 3.11 o superior (usa `tomllib` de la biblioteca estándar).
- [GitHub CLI](https://cli.github.com/) (`gh`) autenticado con una cuenta que sea
  **owner de la organización** del curso.
- El repositorio template debe estar marcado como *template* en GitHub
  (Settings → Template repository).
- El team docente debe existir en la organización.

No hay dependencias que instalar: todo es biblioteca estándar de Python.

### Autenticación

El token de `gh` necesita los scopes **`repo`** y **`admin:org`**. Si te falta
alguno:

```bash
gh auth refresh -h github.com -s admin:org
```

La herramienta valida los scopes antes de empezar y se detiene si falta alguno,
en vez de fallar a mitad de camino con repositorios a medio configurar.

## Puesta en marcha

### 1. Configura el curso

```bash
cp course.example.toml course.toml
```

Edita `course.toml` con los datos de tu curso: organización, repositorio
template, team docente, convención de nombres de los repos, permisos y el texto
del issue de bienvenida. El archivo de ejemplo viene comentado línea por línea.

### 2. Prepara el roster

Exporta tu planilla de alumnos a `roster/roster.csv`. El formato esperado está en
[`roster/roster_example.csv`](roster/roster_example.csv):

| Columna | Descripción |
|---|---|
| `#` | Correlativo del alumno. Solo informativo. |
| `RUT` | Identificador del alumno. No se usa para nada en GitHub. |
| `Nombre` | Nombre del alumno, para los mensajes en pantalla. |
| `Usuario GitHub` | Handle a invitar. Si está vacío, el repo se crea igual y se reporta el caso. |
| `Email` | Correo del alumno. Informativo. |
| `Grupo` | Número de grupo. Determina el nombre del repositorio. |
| `Tamaño Grupo` | Cantidad de integrantes. Se valida contra el conteo real. |
| `Fecha creación repositorio` | **Formato `d/m/aaaa`** (día primero). Decide cuándo se crea el repo. |
| `Ayudante` | Ayudante asignado. Informativo. |

Columnas adicionales al final se ignoran, así que puedes exportar la planilla tal
cual aunque tenga tablas auxiliares pegadas al costado.

**El roster real no se versiona** (contiene datos personales); el `.gitignore` ya
lo excluye.

## Uso

Lo primero, siempre, es una simulación. **Sin `--apply` no se escribe nada en
GitHub:**

```bash
python3 create_repos.py
```

Eso muestra exactamente lo que haría con los grupos cuya fecha es hoy. Cuando el
plan se vea bien:

```bash
python3 create_repos.py --apply
```

Te va a pedir que escribas `si` antes de tocar la organización.

### Ejemplos

```bash
# Simular una fecha distinta a hoy
python3 create_repos.py --date 19/8/2026

# Crear los repos de una fecha específica
python3 create_repos.py --date 19/8/2026 --apply

# Un grupo puntual, ignorando la fecha (p. ej. un alumno que llegó tarde)
python3 create_repos.py --group 22 --apply

# Recuperar fechas ya pasadas que quedaron sin correr
python3 create_repos.py --catch-up --apply

# Otro curso, con su propia configuración y roster
python3 create_repos.py --course cursos/otro.toml --roster rosters/otro.csv
```

### Opciones

| Flag | Efecto |
|---|---|
| `--apply` | Ejecuta de verdad. Sin este flag, solo simula. |
| `--date D/M/AAAA` | Fecha de corte. Por defecto, hoy. |
| `--catch-up` | Incluye también los grupos con fecha anterior a la de corte. |
| `--group N` | Procesa solo ese grupo, ignorando la fecha. Se puede repetir. |
| `--course RUTA` | Archivo de configuración del curso. Por defecto `course.toml`. |
| `--roster RUTA` | CSV del roster. Por defecto `roster/roster.csv`. |
| `--staff-permission` | Sobrescribe el permiso del team docente. |
| `--no-welcome-issue` | No crea el issue de bienvenida. |
| `--yes` | Omite la confirmación interactiva. Solo para uso no interactivo. |
| `--skip-scope-check` | No valida los scopes del token. |

Códigos de salida: `0` todo bien · `1` hubo grupos fallidos o se canceló ·
`2` error de configuración (curso, roster, fecha, token o scopes).

## Se puede correr las veces que quieras

La herramienta es **idempotente**. Si un repositorio ya existe, no lo vuelve a
crear; si un alumno ya fue invitado o ya aceptó, no lo vuelve a invitar; si el
team ya tiene el permiso correcto, no lo toca; si el issue de bienvenida ya está,
no lo duplica.

Eso significa que puedes volver a correrla sin miedo: para completar un grupo que
falló, después de corregir un handle mal escrito en la planilla, o simplemente
para verificar que todo quedó como corresponde.

Un grupo que falle **no detiene a los siguientes**. Al final verás un resumen con
los completos, los que tuvieron advertencias y los fallidos.

## Qué queda registrado

- `logs/` — un archivo por corrida, con todo lo que se hizo o se habría hecho.
- `state/created.json` — último estado conocido de cada repositorio creado.

Ninguno de los dos se versiona.

## Problemas frecuentes

**«al token le faltan los scopes»** — corre el `gh auth refresh` que te indica el
propio mensaje.

**«@usuario no existe en GitHub»** — el handle de la planilla está mal escrito o
el alumno cambió de nombre de usuario. Corrige el CSV y vuelve a correr con
`--group N --apply`.

**«SIN usuario de GitHub»** — el alumno no entregó su handle. El repositorio se
crea igual; cuando tengas el dato, agrégalo al CSV y corre `--group N --apply`
para emitir la invitación.

**Las invitaciones quedan pendientes** — es normal: GitHub las envía por correo y
cada alumno debe aceptarlas. Hasta entonces aparecen como invitaciones, no como
colaboradores.

**Branch protection** — en organizaciones con plan gratuito, las reglas de
protección de rama no están disponibles en repositorios privados. La herramienta
no configura ninguna.
