# AGENTS.md — Correos a los estudiantes

Guía para agentes que trabajen en `assignment-mailings/`. Ver también el
[`AGENTS.md` de la raíz](../AGENTS.md).

## Qué hay

Una instalación base de `mailmerge` (herramienta externa, instalada con pipx, no
un módulo del repositorio) y un helper de biblioteca estándar:

| Archivo | Responsabilidad |
|---|---|
| `mailmerge_server.conf` | Servidor SMTP de Google. Host, puerto, seguridad y usuario. **Nunca la contraseña.** |
| `roster_to_database.py` | Construye `data/<nombre>.csv` desde `course.toml` y el roster; puede cruzar un CSV adicional (credenciales) por correo o por usuario de GitHub. |
| `templates/` | Plantillas de mailmerge. Se versionan. |
| `data/` | Bases de datos CSV. **No se versiona** nada salvo `.keep`. |

## Reglas

- **Nada de `data/` al control de versiones.** El `.gitignore` de la raíz ignora
  `assignment-mailings/data/*` y exceptúa `.keep`. Si agregas otra salida con datos
  de alumnos, ponla en `data/` o agrégala al `.gitignore`.
- **La contraseña de aplicación no se escribe en ningún archivo**, ni en el `.conf`,
  ni en un `.env`, ni en un log. mailmerge la pide por terminal en cada envío.
- **Ningún envío real sin confirmación explícita del usuario en la conversación**, con
  la cuenta exacta de correos que saldrán. Un correo a un estudiante no se puede
  retirar. La secuencia es siempre: `--dry-run --limit 1`, luego `--no-dry-run
  --limit 1` a una dirección de prueba o al primer destinatario, y solo después
  `--no-dry-run --no-limit`.
- **Las plantillas no llevan datos de una persona.** Todo lo personal viene de la
  base de datos por `{{campo}}`. Una plantilla con un nombre o un correo pegado es un
  error.
- **El helper solo lee el roster y `course.toml` y escribe en `data/`.** No importa
  módulos de las otras herramientas: la relación es por los archivos compartidos de
  la raíz, como en el resto del repositorio.
- Python 3.11+ y solo biblioteca estándar en el código propio. `mailmerge` se invoca
  como CLI; no se importa.

## Cómo probar un cambio

1. `python3 roster_to_database.py --salida prueba.csv` y revisar columnas y filas.
2. `mailmerge --template … --database data/prueba.csv --config mailmerge_server.conf
   --dry-run --limit 1`: destinatario, asunto y campos reemplazados.
3. Borrar `data/prueba.csv` si no se va a usar.
