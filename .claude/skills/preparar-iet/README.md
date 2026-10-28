# Skill `preparar-iet`

Prepara el **ítem de evaluación de tarea (IET)** de cada grupo: toma el problema que
marcaste en su `QUESTIONS.md` y produce el enunciado que responden los estudiantes y
la pauta con la que corrigen los ayudantes, en markdown y en PDF.

Es la etapa que sigue a [`preguntas-revision`](../preguntas-revision/): aquella deja
tres problemas candidatos por grupo; tú marcas uno; esta skill lo convierte en
documentos listos para imprimir.

```
assignment-assessment/output/<SIGLA-CURSO>/<TAREA>/grupo-XX/
├── QUESTIONS.md     ← minuta con los tres candidatos y tu marca [x]  (entrada)
├── STATEMENT.md     ← enunciado para los estudiantes                  (salida)
├── STATEMENT.pdf
├── SOLUTION.md      ← pauta de corrección para los ayudantes          (salida)
└── SOLUTION.pdf
```

## Requisitos

1. **Minutas generadas** con `preguntas-revision`.
2. **Un problema marcado por grupo**, con `[x]`, en la sección «Selección para la
   evaluación» de cada `QUESTIONS.md`:

   ```markdown
   - [ ] Problema 1 — Round-robin por nivel en el scheduler
   - [x] Problema 2 — Contabilidad, democión y boost en `mlfq_tick`
   - [ ] Problema 3 — Validación del arreglo de usuario en `getprocs`
   ```

3. Para los PDF, un navegador de la familia Chromium instalado: **Google Chrome**,
   Chromium, Brave o Microsoft Edge. Se busca en el `PATH` y en `/Applications`. Sin
   navegador se generan igual los markdown.

## Cómo se invoca

Desde Claude Code, en cualquier directorio del repositorio:

```
/preparar-iet
```

Sin argumentos trabaja sobre las minutas de la **última descarga** y genera los
documentos de todos los grupos que tengan un problema marcado. También en lenguaje
natural: «prepara el IET de la tarea 1», «genera los enunciados y las pautas».

| Argumento | Para qué |
|---|---|
| `--curso SIGLA --tarea NOMBRE` | Otra tarea: `output/<SIGLA>/<NOMBRE>`. |
| `--dir DIR` | Directorio de minutas explícito. |
| `--group N` | Solo ese grupo. Repetible. |
| `--rehacer` | Sobrescribe `STATEMENT.md`/`SOLUTION.md` ya existentes. |
| `--sin-pdf` | Solo los markdown. |
| `--papel letter\|a4` | Tamaño de página de los PDF. Por defecto, `letter`. Vale también para `pdf`. |

```
/preparar-iet
/preparar-iet --group 7
/preparar-iet --curso ICC3201 --tarea tarea-2
/preparar-iet --group 4 --rehacer
```

## Qué produce

**`STATEMENT.md` / `STATEMENT.pdf`** — el enunciado que responde cada estudiante:

- Cabecera con curso, tarea, número de grupo, integrantes, ayudante y puntaje total
  con su reparto; una línea para el nombre del estudiante.
- Instrucciones: respuesta individual, con lápiz y papel, sin enunciado de la tarea
  ni código; todo lo necesario está en el documento.
- El problema elegido tal como está en la minuta: fragmentos con su
  `archivo:líneas` y commit, citas textuales del enunciado de la tarea,
  definiciones del código base que hagan falta, y las sub-partes con su puntaje.

**`SOLUTION.md` / `SOLUTION.pdf`** — la pauta para el ayudante:

- La misma cabecera, más repositorio, commit revisado y schema.
- El problema completo, para corregir con el enunciado a la vista.
- La pauta: por sub-parte, respuesta esperada, qué vale el puntaje completo y el
  parcial, y señales de alerta.
- Una tabla de registro de puntaje con una fila por sub-parte.

Si la minuta usó la solución canónica (grupo sin avance), el enunciado dice que los
fragmentos son de la solución de referencia y la pauta lo recuerda.

Nada de esto se versiona: `output/` está en el `.gitignore` de la raíz.

## El script

`scripts/iet.py` hace todo el trabajo determinista: lee las minutas, detecta la
marca, arma los dos markdown y los renderiza. Solo biblioteca estándar; el PDF sale
de un navegador headless al que se le pasa un HTML generado por el propio script.

```bash
# Desde la raíz del repositorio
python3 .claude/skills/preparar-iet/scripts/iet.py listar
python3 .claude/skills/preparar-iet/scripts/iet.py listar --curso ICC3201 --tarea tarea-1
python3 .claude/skills/preparar-iet/scripts/iet.py generar --group 7
python3 .claude/skills/preparar-iet/scripts/iet.py generar --rehacer --sin-pdf
python3 .claude/skills/preparar-iet/scripts/iet.py pdf --group 7
```

| Subcomando | Qué hace |
|---|---|
| `listar` | Por grupo: qué problema está marcado (o `sin marcar`, `2 marcados (!)`), su título y qué archivos ya existen. Dice también si hay navegador para los PDF. |
| `generar` | Escribe `STATEMENT.md`, `SOLUTION.md` y sus PDF para los grupos con marca única. No pisa markdown existentes salvo `--rehacer`. |
| `pdf` | Re-renderiza los PDF desde los markdown que ya están en disco. Útil si editaste un `STATEMENT.md` a mano. |

### Editar a mano

La fuente es `QUESTIONS.md`. Si el enunciado necesita un cambio, hazlo ahí y vuelve a
generar con `--rehacer`; así el enunciado y la pauta siguen coincidiendo. Si
prefieres retocar `STATEMENT.md` directamente, `generar` no lo va a pisar sin
`--rehacer`, y `pdf` re-renderiza tu versión.

## Después: imprimir

Con los `STATEMENT.pdf` listos, la skill
[`preparar-impresion-iet`](../preparar-impresion-iet/) los junta en un solo PDF a
doble cara, en orden de grupo y con una copia por integrante, tras comprobar contra
el roster que nadie quede sin enunciado.

## Problemas frecuentes

**«sin marcar» / «2 marcados (!)»** — falta la marca `[x]` en esa minuta, o hay más de
una. La skill no elige por ti: corrige la minuta y vuelve a correr.

**«sin lista de selección (formato antiguo)»** — la minuta se generó con una versión
anterior de `preguntas-revision`, sin la sección «Selección para la evaluación».
Regenérala con `/preguntas-revision --group N --rehacer`.

**«no se encontró Google Chrome, Chromium, Brave ni Edge»** — instala uno (en macOS,
Google Chrome en `/Applications` basta) y corre `iet.py pdf` para producir los PDF de
los markdown que ya quedaron escritos.

**El PDF tarda o el navegador queda abierto** — el script vigila el archivo y cierra
el navegador cuando el PDF deja de crecer; si un proceso quedara colgado, se puede
matar sin perder nada.

**«No hay corrida previa»** — no hay registro de la última descarga. Indica el
directorio con `--curso SIGLA --tarea NOMBRE` o con `--dir`.
