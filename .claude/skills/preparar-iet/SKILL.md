---
name: preparar-iet
description: Prepara el ítem de evaluación de tarea (IET) de cada grupo a partir de las minutas QUESTIONS.md que generó preguntas-revision. Toma el problema que el docente marcó con [x] y escribe en el directorio del grupo STATEMENT.md (enunciado para los estudiantes), SOLUTION.md (pauta para los ayudantes) y sus PDF. Úsala cuando el usuario pida preparar o generar el IET, los enunciados o las pautas de la evaluación de una tarea, o los PDF de la revisión. Se activa con "preparar el IET", "enunciados del IET", "STATEMENT.md", "SOLUTION.md", "pauta de corrección", "generar los PDF de la evaluación".
---

# Preparar el ítem de evaluación de tarea (IET)

Convierte, para cada grupo, el problema que el docente marcó en su `QUESTIONS.md`
en dos documentos listos para usar: el **enunciado** que responde cada estudiante
con lápiz y papel, sin acceso al código ni al enunciado de la tarea, y la **pauta**
con la que los ayudantes corrigen. Ambos se escriben en markdown y en PDF, en el
mismo directorio del grupo.

Casi todo el trabajo es determinista y lo hace `scripts/iet.py`. Tu parte es
correrlo, resolver lo que el script no puede decidir (qué problema eligió el
docente) y leer el resultado con ojos de estudiante antes de darlo por bueno.

No evalúas, no eliges el problema por el docente y no escribes nada en GitHub.

## Antes de empezar

Las minutas tienen que existir y tener **un** problema marcado con `[x]` en su
sección «Selección para la evaluación». Si no hay minutas, dile al usuario que corra
primero la skill `preguntas-revision`. Si una minuta no tiene marca, o tiene más de
una, **no elijas tú**: infórmalo y sigue con las demás.

## Argumentos que puede traer la invocación

| Argumento | Efecto |
|---|---|
| `--curso SIGLA --tarea NOMBRE` | Directorio `assignment-assessment/output/<SIGLA>/<NOMBRE>`. Sin ellos se usa el de la última descarga. |
| `--dir DIR` | Directorio de minutas explícito. |
| `--group N` | Solo ese grupo. Repetible. Sin él, todos los que tengan marca. |
| `--rehacer` | Sobrescribe `STATEMENT.md`/`SOLUTION.md` ya existentes. Sin él se saltan. |
| `--sin-pdf` | Solo los markdown. |
| `--papel letter\|a4` | Tamaño de página de los PDF. Por defecto, `letter`. Vale también para `pdf`. |

## Procedimiento

`SCRIPT` es `.claude/skills/preparar-iet/scripts/iet.py` (ruta relativa a la raíz del
repositorio).

### 1. Revisa el estado de las minutas

```bash
python3 SCRIPT listar [--curso SIGLA --tarea NOMBRE | --dir DIR]
```

Muestra, por grupo, qué problema está marcado (`P2 marcado`, `sin marcar`,
`2 marcados (!)`, formato antiguo sin lista de selección), el título del problema
elegido y qué archivos ya existen. También dice si encontró un navegador para los
PDF.

Anota los grupos sin marca única: van al resumen final como pendientes del docente.
Si **ninguno** tiene marca, detente y díselo al usuario; no hay nada que generar.

### 2. Genera los documentos

```bash
python3 SCRIPT generar [--group N ...] [--rehacer] [--sin-pdf] [--papel letter|a4]
```

Por cada grupo con marca única escribe `STATEMENT.md`, `SOLUTION.md`,
`STATEMENT.pdf` y `SOLUTION.pdf` en `grupo-XX/`. No pisa markdown existentes salvo
`--rehacer`, porque el docente puede haberlos editado a mano.

Si el script avisa que no encontró navegador (Google Chrome, Chromium, Brave o
Edge), los markdown quedan igual; dile al usuario qué instalar y ofrece volver a
correr `python3 SCRIPT pdf` después.

### 3. Lee cada enunciado como lo leería un estudiante

Abre cada `STATEMENT.md` generado y comprueba, sin mirar el `QUESTIONS.md`:

- Que se entienda **sin el código ni el enunciado de la tarea**: todo fragmento
  necesario está citado, toda regla a la que se alude aparece bajo «Del enunciado
  de la tarea», y las constantes o firmas del código base que usan las preguntas
  están definidas en el texto.
- Que no haya referencias a otros problemas («como en el problema 1») ni a la
  sección para el revisor.
- Que las sub-partes traigan su puntaje y sumen el total del encabezado.

Si algo falla, **corrige la fuente** (`QUESTIONS.md` del grupo) y vuelve a generar
ese grupo con `--rehacer`. No edites `STATEMENT.md` a mano: se perdería en la
próxima corrida. La excepción es que el usuario te lo pida explícitamente; en ese
caso edita el markdown y re-renderiza con `python3 SCRIPT pdf --group N`.

Abre también una `SOLUTION.md` y verifica que la pauta corresponda al mismo
problema que el enunciado y que la tabla de puntaje tenga una fila por sub-parte.

### 4. Comprueba los PDF

Confirma que existen los cuatro archivos por grupo. Si `pdftoppm` está disponible,
rasteriza la primera página de un `STATEMENT.pdf` (`pdftoppm -r 60 -png -f 1 -l 1`)
en el scratchpad y mírala: el título, la cabecera y el primer fragmento deben verse
completos y legibles. No hace falta revisar todos.

### 5. Cierra

Informa en una tabla corta: grupo, problema elegido (número y título) y archivos
escritos. Aparte, los grupos saltados y por qué (sin marca, varias marcas, archivos
existentes sin `--rehacer`, minuta en formato antiguo) y, si aplica, que faltó el
navegador para los PDF.

## Errores comunes

- **Elegir el problema por el docente.** Si no hay marca única, el grupo se salta y
  se informa. La decisión es del docente.
- **Arreglar el enunciado a mano.** La fuente es `QUESTIONS.md`; el arreglo va ahí y
  se regenera.
- **Pasar por alto un enunciado que depende del código.** El estudiante no lo
  tendrá. Léelo como estudiante antes de darlo por bueno.
- **Pisar ediciones del docente.** Sin `--rehacer`, los markdown existentes se
  respetan; si el usuario pide regenerar, díselo antes de usar `--rehacer` sobre
  archivos que él pudo haber tocado.
