# Correos a los estudiantes con mailmerge

Envío de correos personalizados a los estudiantes del curso (repositorio asignado,
credenciales, recordatorios) con [mailmerge](https://github.com/awdeorio/mailmerge),
usando la cuenta corporativa de Google del docente.

```
assignment-mailings/
├── mailmerge_server.conf   # servidor SMTP de Google: host, puerto y usuario (sin contraseña)
├── roster_to_database.py   # arma la base de datos de mailmerge desde el roster del curso
├── templates/              # plantillas de correo (se versionan)
│   └── ejemplo-repositorio.txt
└── data/                   # bases de datos CSV con correos y credenciales (NO se versionan)
    └── .keep
```

**Nada de `data/` se versiona** salvo `.keep`: esos CSV traen correos de alumnos y, a
veces, credenciales que se les entregan. La contraseña de aplicación de Google
tampoco se guarda en ningún archivo: mailmerge la pide por terminal en cada envío.

## Requisitos

- Python 3.11 o superior.
- `mailmerge`, instalado aislado con pipx:

  ```bash
  pipx install mailmerge
  pipx ensurepath        # deja ~/.local/bin en el PATH; abre una terminal nueva
  ```

- Una **contraseña de aplicación** de la cuenta de Google que envía. Se crea en
  <https://myaccount.google.com/apppasswords> y requiere verificación en dos pasos.
  No es la contraseña de la cuenta y se puede revocar sin afectarla.

## Cómo funciona mailmerge

Tres archivos: una **plantilla** (texto con cabeceras `TO`, `SUBJECT`, `FROM` y
campos `{{columna}}`), una **base de datos** CSV (una fila por correo, una columna por
campo) y la **configuración del servidor**. Por defecto mailmerge **no envía**: hace
dry-run del primer mensaje y lo muestra. Para enviar hay que pedirlo con
`--no-dry-run`, y para más de un correo, `--no-limit` o `--limit N`.

## Paso a paso

### 1. Arma la base de datos desde el roster

```bash
cd assignment-mailings
python3 roster_to_database.py --salida tarea2.csv
```

Escribe `data/tarea2.csv` con una fila por estudiante y las columnas `email`,
`nombre`, `github`, `grupo`, `repo`, `url` y `ayudante`, tomando la organización y el
nombre de los repos de `course.toml`. Opciones:

| Opción | Para qué |
|---|---|
| `--group N` | Solo esos grupos. Repetible. |
| `--merge CSV --on email` | Cruza otro CSV (por ejemplo, credenciales) y agrega sus columnas. `--on` puede ser `email` o `github`. Avisa de los estudiantes sin fila en ese CSV. |
| `--sin-email-ok` | Omite a quien no tenga correo en el roster en vez de detenerse. |
| `--course`, `--roster` | Otro curso u otro roster. |

Deja el CSV de credenciales también dentro de `data/`, que ya está ignorado.

### 2. Escribe o elige la plantilla

Las plantillas viven en `templates/`. Formato:

```
TO: {{email}}
SUBJECT: [ICC3201] Tu repositorio para la Tarea 2 — grupo {{grupo}}
FROM: Claudio Álvarez <calvarez1@miuandes.cl>

Hola {{nombre}},
…
```

Cada `{{columna}}` se reemplaza por el valor de esa fila de la base de datos. Ver
`templates/ejemplo-repositorio.txt`. Las plantillas se versionan: no pongas en ellas
datos de una persona en particular.

### 3. Prueba en seco

```bash
mailmerge --template templates/ejemplo-repositorio.txt --database data/tarea2.csv \
          --config mailmerge_server.conf --dry-run --limit 1
```

Muestra el primer correo tal como saldría, sin conectarse al servidor. Revisa
destinatario, asunto y que ningún `{{campo}}` haya quedado sin reemplazar. Para ver
más mensajes, sube `--limit`; `--no-limit --dry-run` los muestra todos.

### 4. Envía

Primero **uno**, y confirma que llegó bien (por ejemplo, ponte a ti mismo en la
primera fila de una base de datos de prueba):

```bash
mailmerge --template templates/ejemplo-repositorio.txt --database data/tarea2.csv \
          --config mailmerge_server.conf --no-dry-run --limit 1
```

Pedirá la contraseña de aplicación. Cuando el primer correo esté bien:

```bash
mailmerge --template templates/ejemplo-repositorio.txt --database data/tarea2.csv \
          --config mailmerge_server.conf --no-dry-run --no-limit
```

Si el envío se interrumpe, `--resume N` retoma desde el mensaje N (los mensajes se
numeran desde 1 en el orden del CSV).

## Servidor

`mailmerge_server.conf` está configurado para Google Workspace con SSL/TLS en el
puerto 465 y la cuenta `calvarez1@miuandes.cl`. Google limita los envíos diarios de
una cuenta (del orden de dos mil por día en cuentas Workspace); un curso de treinta
estudiantes está muy lejos de ese límite. Si Google rechaza la autenticación,
comprueba que la contraseña de aplicación siga vigente y que la verificación en dos
pasos esté activa.

## Qué se versiona y qué no

| Archivo | Se versiona |
|---|---|
| `mailmerge_server.conf` | Sí: no contiene la contraseña. |
| `templates/*.txt` | Sí. |
| `roster_to_database.py`, `README.md`, `AGENTS.md` | Sí. |
| `data/*` (salvo `.keep`) | **No**: correos y credenciales. |

El `.gitignore` de la raíz ya aplica estas reglas.
