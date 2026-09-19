---
name: preparar-impresion-iet
description: Arma un solo PDF imprimible con los enunciados del IET (STATEMENT.pdf) de todos los grupos de una tarea, en orden ascendente de grupo, con una copia por integrante según el roster y páginas en blanco de relleno para impresión a doble cara. Antes valida que todo estudiante del roster tenga enunciado y reporta los que no. Úsala cuando el usuario pida imprimir el IET, el PDF único de enunciados, el material para el día de la prueba o comprobar que no falte ningún enunciado. Se activa con "imprimir el IET", "PDF único", "enunciados para imprimir", "preparar la impresión", "¿falta algún enunciado?".
---

# Preparar la impresión del IET

Produce, a partir de los `STATEMENT.pdf` que dejó `preparar-iet`, **un solo PDF** para
mandar a imprimir a doble cara, y un manifiesto con el orden de las hojas. El PDF
sigue el orden ascendente de grupo, para repartir llamando grupo a grupo, y trae
tantas copias de cada enunciado como integrantes tenga el grupo en el roster. Los
enunciados con un número impar de carillas reciben una página en blanco al final,
para que cada copia empiece en hoja nueva.

Casi todo es determinista y lo hace `scripts/imprimir.py`. Tu parte es correrlo,
detenerte si falta algún enunciado y comprobar el resultado.

## Antes de empezar

Hacen falta los `STATEMENT.pdf` de `preparar-iet` y el roster del curso
(`roster/roster.csv`). El script usa `pdfinfo` y `pdfunite` (poppler) o `gs`
(Ghostscript), que se buscan en el `PATH`; si faltan, lo dice y te detienes para
avisar al usuario qué instalar.

## Argumentos que puede traer la invocación

| Argumento | Efecto |
|---|---|
| `--curso SIGLA --tarea NOMBRE` | Directorio `assignment-assessment/output/<SIGLA>/<NOMBRE>`. Sin ellos, el de la última descarga. |
| `--dir DIR` | Directorio de enunciados explícito. |
| `--roster CSV` | Otro roster. Por defecto, `roster/roster.csv`. |
| `--copias N` | Copias fijas por grupo, en vez de una por integrante. |
| `--copias-extra N` | Copias adicionales por grupo, además de una por integrante. |
| `--permitir-faltantes` | Genera el PDF aunque falten enunciados (se informa quiénes quedan fuera). |

## Procedimiento

`SCRIPT` es `.claude/skills/preparar-impresion-iet/scripts/imprimir.py` (ruta relativa
a la raíz del repositorio).

### 1. Valida contra el roster

```bash
python3 SCRIPT validar [--curso SIGLA --tarea NOMBRE | --dir DIR] [--roster CSV]
```

Imprime, por grupo del roster, cuántos integrantes tiene, si existe su
`STATEMENT.pdf`, cuántas carillas tiene y observaciones (integrantes cuyo nombre no
aparece en la cabecera del enunciado, enunciados de grupos que no están en el
roster). Al final lista los **estudiantes sin enunciado**.

Si hay estudiantes sin enunciado, **detente** y díselo al usuario con la lista:
falta correr `preparar-iet` para esos grupos, o el roster y las minutas no
coinciden. No generes el PDF con `--permitir-faltantes` salvo que el usuario lo pida
sabiendo quiénes quedan fuera.

Si hay integrantes que no aparecen en la cabecera de su enunciado, avísalo: suele
ser un roster actualizado después de generar el enunciado, y se corrige regenerando
ese grupo con `preparar-iet --group N --rehacer`.

### 2. Genera el PDF

```bash
python3 SCRIPT generar [--copias-extra N]
```

Escribe `IET-impresion.pdf` y `IET-impresion.md` en el directorio de la tarea. El
`.md` es el orden de impresión: por grupo, integrantes, copias, carillas por copia,
si lleva relleno y en qué hojas queda. El script comprueba que el PDF final tenga
exactamente las carillas esperadas y falla si no.

Si el usuario pide copias de reserva, usa `--copias-extra`; no inventes copias.

### 3. Comprueba

Abre `IET-impresion.md` y confirma que el total de hojas y de copias coincide con
lo que el usuario espera (por ejemplo, 32 copias para 32 estudiantes). Si
`pdftoppm` está disponible, rasteriza en el scratchpad la primera carilla y la que
sigue a la primera copia (`-f 1 -l 1` y la página `carillas_por_copia + relleno + 1`)
para ver que la segunda copia empieza limpia en hoja nueva. No hace falta revisar
todo el PDF.

### 4. Cierra

Informa: ruta del PDF, carillas y hojas totales, copias y grupos, y la lista de
estudiantes sin enunciado si la hubo. Recuerda que la impresión es a doble cara y
que el reparto sigue el orden de grupo del manifiesto.

## Errores comunes

- **Generar con faltantes sin avisar.** Un estudiante sin hoja el día de la prueba
  es lo que esta skill existe para evitar. La lista de faltantes va siempre en el
  informe.
- **Copias por directorio y no por roster.** Las copias salen del roster; un grupo
  de dos recibe dos copias aunque los dos compartan enunciado.
- **Olvidar el relleno.** Sin la página en blanco, la copia siguiente empezaría al
  dorso de la anterior.
