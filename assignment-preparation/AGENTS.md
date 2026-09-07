# AGENTS.md — Herramienta de creación de repositorios de grupo

Guía para agentes que trabajen en `assignment-preparation/`. Léela completa antes
de tocar código o de ejecutar cualquier comando contra GitHub.

Este es uno de los proyectos del repositorio `github-teaching-tools`; el otro es
`assignment-assessment/`, que es independiente. Las reglas de acá aplican a este
directorio.

Para la guía de uso orientada al usuario, ver [README.md](README.md).

## 1. Qué es esta herramienta

Un CLI que, a partir de (a) la configuración de un curso y (b) una planilla de
alumnos con sus grupos, crea y configura los repositorios de proyecto de cada grupo
en una organización de GitHub, y mantiene al día las invitaciones de sus integrantes.

Son dos entrypoints sobre los mismos módulos:

- `create_repos.py` — crea y configura los repos de los grupos de una fecha.
- `resend_invitations.py` — reenvía las invitaciones caducadas de los repos ya
  creados, sin filtrar por fecha. Ver §9.

Es **genérica**: no está atada a un curso, organización, template ni team en
particular. Todo eso es configuración. El mismo código sirve para cualquier curso que
siga este modelo:

> Cada grupo recibe un repositorio propio, generado desde un repositorio template
> común, al que se invita a sus integrantes y al que el equipo docente tiene acceso
> vía un team de la organización.

La ejecuta **una persona, a mano**, en la fecha que corresponda. No es un cron, ni un
servicio, ni un workflow de CI. Cualquier cambio que la convierta en algo desatendido
requiere autorización explícita.

## 2. Arquitectura

```
github-teaching-tools/
├── course.toml               # curso activo — COMPARTIDO, en la raíz (no se versiona)
├── course.example.toml       # plantilla documentada de course.toml
├── roster/                   # COMPARTIDO, en la raíz
│   ├── roster.csv                # roster real (NO se versiona)
│   └── roster_example.csv        # formato esperado, con datos ficticios
└── assignment-preparation/
    ├── config.py         # carga course.toml y expone sus valores + constantes del CLI
    ├── roster_loader.py  # parseo y validación del CSV → Student / Group
    ├── github_api.py     # cliente HTTP sobre stdlib; separa lecturas de escrituras
    ├── runio.py          # salidas en disco de una corrida: Logger y estado JSON
    ├── create_repos.py       # entrypoint: creación de repos por fecha
    ├── resend_invitations.py # entrypoint: reenvío de invitaciones caducadas
    ├── logs/             # un .log por corrida (generado)
    └── state/
        ├── created.json      # último estado por repo creado (generado)
        └── invitations.json  # último reenvío por repo (generado)
```

**El curso y el roster son entradas compartidas del repositorio y viven en la raíz**;
`logs/` y `state/` son salidas de esta herramienta y viven acá. `config.py` resuelve
lo compartido contra `REPO_ROOT = BASE_DIR.parent` y lo propio contra `BASE_DIR`; al
agregar una ruta, decide a cuál de los dos pertenece. La herramienta se ejecuta desde
`assignment-preparation/`, así que los mensajes que muestran rutas al usuario usan
`config.display_path()` y no `Path.name`.

Reglas de arquitectura:

- **Sin dependencias externas.** Solo stdlib (`csv`, `tomllib`, `argparse`, `urllib`,
  `json`) más `subprocess` para leer el token de `gh`. No introducir un
  `requirements.txt` ni frameworks salvo necesidad real y conversada.
- **Nada específico de un curso en el código.** Si aparece un nombre de organización,
  de template, de team o una convención de nombres hardcodeada en un `.py`, es un bug:
  va en `course.toml`.
- **La invitación idempotente vive en un solo lugar:** `GitHubClient.
  ensure_collaborator()`. Los dos entrypoints la usan. No reimplementar la
  decisión de invitar/reenviar/omitir en un entrypoint: el bug de las
  invitaciones vencidas apareció justamente por tener esa política suelta.
- **`config.py` es la única puerta a la configuración.** El resto del código usa
  `config.ORG`, `config.repo_name(n)`, etc., sin saber que existe un TOML.
  `config.load_course(path)` repuebla esas constantes; por eso los defaults de
  argparse que dependen del curso se resuelven **después** de cargarlo, no al
  construir el parser.
- **Estructura plana.** Cuatro módulos de apoyo y dos entrypoints, todos al mismo
  nivel. No crear paquetes ni capas. Un entrypoint nuevo no importa a otro
  entrypoint: lo que compartan va a un módulo (así nació `runio.py`).
- **No importar código de `assignment-assessment/`** ni exponerle módulos de acá. Si
  algo se necesita en ambos, conversarlo antes: lo compartido hoy son los datos
  (`course.toml`, `roster/`), no el código.
- El módulo se llama `roster_loader.py` y no `roster.py` para no colisionar con el
  directorio `roster/`.

## 3. El contrato del roster

El esquema del CSV es parte del contrato de la herramienta y **no es configurable**.
Columnas requeridas: `#`, `Nombre`, `Usuario GitHub`, `Grupo`, `Tamaño Grupo`,
`Fecha creación repositorio`. Opcionales: `RUT`, `Email`, `Ayudante`.

Ver [`roster/roster_example.csv`](../roster/roster_example.csv) y el README para la
descripción de cada columna.

**Un roster por curso.** `[course] roster` de `course.toml` apunta al CSV de ese
curso, relativo a `REPO_ROOT`; si falta, se usa `roster/roster.csv`. Los defaults de
argparse que dependen de esto (`--roster`) se resuelven **después** de
`load_course()`, igual que `--staff-permission`. Con dos cursos activos, un roster
único invitaría a los alumnos de un curso a los repos del otro.

Estos archivos vienen de exports de planilla, así que el parser debe seguir siendo
tolerante a:

- **Columnas fantasma al final**, sin encabezado o con encabezados vacíos duplicados,
  que traen tablas auxiliares pegadas al costado de la planilla. Se ignoran.
- **Fechas en formato `d/m/aaaa`** (día primero, convención chilena). Parsear con
  `%d/%m/%Y`. **Nunca** asumir ISO ni mes-primero: `8/9/2026` es 8 de septiembre.
- **Espacios accidentales** en cualquier campo (`LETELIER /CASTRO`). Aplicar `.strip()`.
- **Identificadores con letras** (RUT terminado en `K`). No parsear como entero.
- **Mayúsculas inconsistentes** en correos y handles. Normalizar con `.lower()` para
  comparar; enviar el valor original.
- **Campos vacíos**, en particular `Usuario GitHub`.

El parser **valida y advierte** sin abortar: tamaño de grupo que no calza con el
conteo real, fechas o ayudantes distintos entre integrantes del mismo grupo, números
de grupo faltantes, handles repetidos en más de una fila, integrantes sin handle. Los
errores duros (archivo ausente, columna requerida faltante, grupo no numérico, fecha
inválida) levantan `RosterError` y detienen la corrida antes de tocar GitHub.

## 4. El proceso

Para cada grupo seleccionado, **en orden ascendente de número de grupo**:

1. **Crear el repositorio** desde el template.
   `POST /repos/{template_owner}/{template_repo}/generate`
2. **Invitar a cada integrante** con el permiso configurado.
   `PUT /repos/{org}/{repo}/collaborators/{username}`
3. **Dar acceso al team docente**.
   `PUT /orgs/{org}/teams/{team}/repos/{org}/{repo}`
4. **Abrir el issue de bienvenida** con las instrucciones de `upstream`.
   `POST /repos/{org}/{repo}/issues`
5. **Registrar el resultado** en `state/created.json` y en el log de la corrida.

Selección de grupos: por defecto, los que tienen fecha **igual** a la de corte;
con `--catch-up`, también los anteriores; con `--group N`, esos y solo esos.

### Invariantes no negociables

- **Dry-run por defecto.** Sin `--apply` no se escribe nada. Las lecturas sí se
  ejecutan, porque son inocuas y hacen que la simulación sea realista.
- **Confirmación explícita** antes de escribir, incluso con `--apply`. `--yes` la
  omite y existe solo para uso no interactivo.
- **Idempotencia.** Volver a correr no debe fallar ni duplicar nada. Antes de cada
  escritura se consulta el estado actual: repo existente, colaborador ya invitado o ya
  aceptado, permiso de team ya correcto, issue ya creado.
- **Una invitación vencida no es una invitación pendiente.** GitHub caduca las
  invitaciones a los 7 días y las **deja en el listado** de
  `GET /repos/{org}/{repo}/invitations`, con `expired: true`. Tratarlas como
  pendientes deja al alumno afuera para siempre, que es exactamente el bug que
  tenía esta herramienta. Reemitir el `PUT` sobre una invitación existente no
  reinicia su plazo: hay que borrarla (`DELETE .../invitations/{id}`) y emitir otra.
- **Aislamiento de fallos.** Un grupo que falla no aborta los siguientes. El resumen
  final distingue completos, con advertencias y fallidos.
- **Filtrado por fecha estricto.** Nunca crear repos de una fecha futura. La fecha de
  corte sale del sistema, con override explícito `--date`.
- **Fallar temprano.** Configuración, roster, token y scopes se validan **antes** de
  la primera escritura, para no dejar repositorios a medio configurar.
- **Reintentos con backoff** ante 429, 5xx y 403 por rate limit (no ante 403 por
  permisos). Tras `generate`, el repo puede responder 404 unos segundos: hay que
  esperar a que aparezca.

## 5. Autenticación

El token se obtiene con `gh auth token` en runtime. Scopes requeridos: **`repo`** y
**`admin:org`** (este último es el que permite asociar un team a un repositorio).

La validación lee el header `X-OAuth-Scopes`. Los tokens fine-grained no lo exponen:
en ese caso la validación se salta en vez de bloquear.

**Nunca** escribir el token en un archivo, en el log ni en un `.env` versionado.

## 6. Datos sensibles

El roster contiene identificadores nacionales y correos de estudiantes.

- `roster/*.csv` está en el `.gitignore` de la raíz, con excepción de
  `roster_example.csv`. Lo mismo con `course.*.toml`, salvo `course.example.toml`.
- El `RUT` se lee pero **no se almacena** en la dataclass `Student`: no se necesita
  para ninguna operación de GitHub.
- No loguear RUTs ni correos más allá de lo mínimo para identificar un problema.
- No subir el CSV, ni RUTs, ni correos, ni tokens a ningún repositorio remoto.

## 7. Qué NO hacer

- No ejecutar escrituras contra una organización sin confirmación explícita del
  usuario en esta conversación, aunque el flag `--apply` esté en el comando. Crear
  repositorios e invitar estudiantes es visible para terceros y molesto de revertir.
- No borrar, renombrar ni cambiar la visibilidad de repositorios existentes.
- No configurar branch protection ni rulesets salvo petición explícita. El modelo por
  defecto es permisivo: los integrantes empujan directo a la rama principal y los PRs
  quedan como herramienta opcional de coordinación y entrega.
- No inventar handles de GitHub ni "corregirlos" por parecido de nombre. Si un handle
  no existe, reportarlo y dejar que el profesor lo resuelva.
- No invitar a nadie sin haber comprobado que el roster corresponde a la
  organización del curso. Cada invitación manda un correo a una persona real y no
  se puede "desenviar".
- No cambiar el formato de fecha del CSV a ISO ni reordenar sus columnas.
- No convertir esto en un servicio desatendido.

## 8. Al agregar funcionalidad

Toda operación nueva sobre GitHub debe cumplir los invariantes de §4: pasar por
`_write()` para respetar el dry-run, consultar el estado antes de escribir para
seguir siendo idempotente, y quedar registrada en el record del grupo.

Todo texto o convención que un curso distinto querría cambiar va a `course.toml` y a
`course.example.toml`, documentado. Si agregas una clave, actualiza ambos archivos y
la tabla del README.

Antes de dar por terminado un cambio, verifica al menos: un dry-run completo, el
camino de idempotencia (segunda corrida sobre algo ya creado) y los caminos de error
(configuración inválida, roster ausente, fecha mal formada).

## 9. El reenvío de invitaciones

`resend_invitations.py` existe porque las invitaciones caducan (§4) y porque
`create_repos.py` está atado a la fecha de creación del roster, que no dice nada
sobre cuándo caduca una invitación.

Diferencias de diseño respecto de `create_repos.py`, todas deliberadas:

- **No filtra por fecha.** Revisa todos los grupos del roster, o los de `--group`.
- **No crea nada.** Si el repo no existe, lo reporta y sigue. Crear es de la otra
  herramienta.
- **Diagnostica primero, escribe después.** La fase de plan es solo lecturas y corre
  igual con `--apply`; recién después se confirma, con la **cuenta exacta** de correos
  que se van a mandar, y se ejecuta. La ejecución vuelve a pasar por
  `ensure_collaborator()`, así que si el alumno aceptó entre el plan y la
  confirmación, no se lo invita de nuevo.
- **Guarda contra el roster equivocado.** El plan también mira quién tiene acceso hoy
  al repo, descontando al team docente y a quien tenga `admin`/`maintain`. Si en más
  de la mitad de los repos revisados ningún integrante del roster tiene acceso y sí lo
  tienen personas ajenas al roster, la corrida se detiene con código `2`
  (`--ignore-roster-mismatch` para forzar). Sin esta guarda, un `--course` de un curso
  con el roster de otro le manda correo a un curso completo equivocado.

Su estado va a `state/invitations.json` y su log lleva `-invites-` en el nombre, para
no pisar los de la creación de repos.
