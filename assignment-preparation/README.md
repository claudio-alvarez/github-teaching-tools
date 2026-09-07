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

Y como las invitaciones de GitHub **caducan a los 7 días**, incluye un segundo
comando que las reenvía a quien no alcanzó a aceptar: ver
[Reenviar invitaciones caducadas](#reenviar-invitaciones-caducadas).

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

La configuración del curso y el roster viven **en la raíz del repositorio**,
porque los comparten todas las herramientas. Los comandos, en cambio, se ejecutan
desde este directorio:

```
github-teaching-tools/
├── course.toml               # configuración del curso (acá)
├── roster/roster.csv         # planilla de alumnos (acá)
└── assignment-preparation/   # desde acá se corre la herramienta
```

### 1. Configura el curso

Desde la raíz del repositorio:

```bash
cp course.example.toml course.toml
```

Edita `course.toml` con los datos de tu curso: organización, repositorio
template, team docente, convención de nombres de los repos, permisos y el texto
del issue de bienvenida. El archivo de ejemplo viene comentado línea por línea.

### 2. Prepara el roster

Exporta tu planilla de alumnos a `roster/roster.csv`, también en la raíz. El
formato esperado está en [`roster/roster_example.csv`](../roster/roster_example.csv):

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

**Si tienes más de un curso activo, cada uno necesita su propio CSV**: los alumnos
son distintos. Deja los archivos en `roster/` (por ejemplo
`roster/roster.ICC4203-202620.csv`) y que cada `course*.toml` apunte al suyo:

```toml
[course]
roster = "roster/roster.ICC4203-202620.csv"   # relativo a la raíz del repositorio
```

Sin esa clave se usa `roster/roster.csv`. `--roster` sigue mandando por sobre las dos
cosas.

**El roster real no se versiona** (contiene datos personales); el `.gitignore` de
la raíz ya lo excluye, igual que `course.toml`.

## Uso

Lo primero, siempre, es una simulación. **Sin `--apply` no se escribe nada en
GitHub:**

```bash
cd assignment-preparation
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

# Otro curso, con su propia configuración y su propio roster
python3 create_repos.py --course ../course.otro.toml
```

### Opciones

| Flag | Efecto |
|---|---|
| `--apply` | Ejecuta de verdad. Sin este flag, solo simula. |
| `--date D/M/AAAA` | Fecha de corte. Por defecto, hoy. |
| `--catch-up` | Incluye también los grupos con fecha anterior a la de corte. |
| `--group N` | Procesa solo ese grupo, ignorando la fecha. Se puede repetir. |
| `--course RUTA` | Archivo de configuración del curso. Por defecto `course.toml`. |
| `--roster RUTA` | CSV del roster. Por defecto, el que declare el curso. |
| `--staff-permission` | Sobrescribe el permiso del team docente. |
| `--no-welcome-issue` | No crea el issue de bienvenida. |
| `--yes` | Omite la confirmación interactiva. Solo para uso no interactivo. |
| `--skip-scope-check` | No valida los scopes del token. |

Códigos de salida: `0` todo bien · `1` hubo grupos fallidos o se canceló ·
`2` error de configuración (curso, roster, fecha, token o scopes).

## Reenviar invitaciones caducadas

**Las invitaciones a colaborar en un repositorio caducan a los 7 días.** GitHub las
deja en el listado del repositorio marcadas como vencidas, así que el alumno que no
alcanzó a aceptar queda afuera y no se arregla solo: hay que borrar la invitación
vencida y emitir otra.

`resend_invitations.py` compara el roster con el estado real de cada repositorio y
actúa **solo sobre quien le falta invitación**:

```bash
cd assignment-preparation

# Diagnóstico: quién quedó afuera y por qué. No escribe nada.
python3 resend_invitations.py

# Reenviar (pide confirmación y te muestra la cuenta exacta de correos)
python3 resend_invitations.py --apply

# Solo un par de grupos
python3 resend_invitations.py --group 4 --group 12 --apply

# El otro curso
python3 resend_invitations.py --course ../course.ICC4203-202620.toml --apply
```

A diferencia de `create_repos.py`, este comando **no filtra por fecha**: revisa todos
los grupos del roster, porque la caducidad no sigue el calendario de creación. Tampoco
crea repositorios; si a un grupo le falta el suyo, lo reporta y te manda a
`create_repos.py`.

Para cada integrante decide así:

| Estado en GitHub | Qué hace |
|---|---|
| Ya aceptó (es colaborador) | Nada. |
| Invitación pendiente y vigente | Nada, salvo que uses `--renew-pending`. |
| Invitación **vencida** | La borra y emite una nueva. |
| Sin invitación ni acceso | Lo invita. |
| Sin handle en el roster, o handle inexistente | Lo reporta para que lo resuelvas tú. |

### Opciones

| Flag | Efecto |
|---|---|
| `--apply` | Ejecuta de verdad. Sin este flag, solo diagnostica. |
| `--group N` | Revisa solo ese grupo. Se puede repetir. Por defecto, todos. |
| `--renew-pending` | Reemite también las invitaciones vigentes, reiniciando su plazo. |
| `--ignore-roster-mismatch` | Continúa aunque el roster no parezca ser el de esta organización. |
| `--course RUTA` | Archivo de configuración del curso. Por defecto `course.toml`. |
| `--roster RUTA` | CSV del roster. Por defecto, el que declare el curso. |
| `--yes` | Omite la confirmación interactiva. Solo para uso no interactivo. |
| `--skip-scope-check` | No valida los scopes del token. |

Códigos de salida: `0` todo bien · `1` hubo grupos fallidos o se canceló ·
`2` error de configuración, o el roster no corresponde a la organización.

### La guarda del roster equivocado

Con dos cursos activos, correr el reenvío con el `course.toml` de uno y el roster del
otro le mandaría correo a treinta alumnos que no son de ese curso. Para que eso no
pase, el diagnóstico también mira **quién tiene acceso hoy** a cada repositorio: si en
más de la mitad de los repos revisados ningún integrante del roster tiene acceso y sí
lo tienen personas ajenas al roster, la corrida se detiene con código `2` antes de
preguntarte nada.

Ese mismo chequeo sirve de paso para detectar alumnos que cambiaron de grupo o que
fueron invitados al repositorio equivocado: aparecen como
`! con acceso de integrante pero FUERA del roster`.

Las invitaciones nuevas también caducan en 7 días. Conviene avisarles a los alumnos
en el mismo momento en que corres el comando.

## Se puede correr las veces que quieras

Las dos herramientas son **idempotentes**. Si un repositorio ya existe, no lo
vuelve a crear; si un alumno ya aceptó o tiene una invitación vigente, no lo
vuelve a invitar; si el team ya tiene el permiso correcto, no lo toca; si el issue
de bienvenida ya está, no lo duplica.

La única excepción, a propósito, son las **invitaciones vencidas**: esas sí se
reemiten, porque dejarlas como están equivale a dejar al alumno afuera del curso.
`create_repos.py` también las detecta y las reenvía cuando pasa por un repo que ya
existía.

Eso significa que puedes volver a correrla sin miedo: para completar un grupo que
falló, después de corregir un handle mal escrito en la planilla, o simplemente
para verificar que todo quedó como corresponde.

Un grupo que falle **no detiene a los siguientes**. Al final verás un resumen con
los completos, los que tuvieron advertencias y los fallidos.

## Qué queda registrado

- `logs/` — un archivo por corrida, con todo lo que se hizo o se habría hecho.
  Los del reenvío de invitaciones llevan `-invites-` en el nombre.
- `state/created.json` — último estado conocido de cada repositorio creado.
- `state/invitations.json` — último reenvío de invitaciones por repositorio.

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

**«invitación VENCIDA»** — el alumno no aceptó dentro de los 7 días que da GitHub.
Corre `python3 resend_invitations.py --apply`; ver
[Reenviar invitaciones caducadas](#reenviar-invitaciones-caducadas).

**«el roster no parece corresponder a esta organización»** — estás usando el
`course.toml` de un curso con el roster de otro. Revisa la clave `roster` de
`[course]` o pasa `--roster` con el CSV correcto.

**Branch protection** — en organizaciones con plan gratuito, las reglas de
protección de rama no están disponibles en repositorios privados. La herramienta
no configura ninguna.
