---
name: preguntas-revision
description: Genera la minuta de problemas de revisión de código (QUESTIONS.md) para cada grupo de un curso, a partir de los repositorios ya descargados con assignment-assessment/clone_repos.py. Cada minuta trae tres problemas candidatos de 10 puntos, con sub-partes definidas por un schema, de los que el docente marca uno. Úsala cuando el usuario pida preguntas o problemas de revisión, interrogar a los grupos sobre su código, preparar la revisión presencial de una tarea, el ítem de evaluación teórica (IET) o entrevistas de código. Se activa con "preguntas de revisión", "problemas de revisión", "minutas de los grupos", "QUESTIONS.md", "revisar las entregas del grupo N", "preguntas para la entrevista de código".
---

# Problemas de revisión de código por grupo

Produces, para cada grupo, un `QUESTIONS.md` con **tres problemas candidatos**
sobre el código que el grupo entregó. Cada problema se ancla a un fragmento concreto
del repositorio, vale **10 puntos** repartidos en sub-partes según un **schema**, y
sirve para distinguir a quien entiende lo que entregó de quien no.

Los tres problemas son candidatos: el docente **marca uno** en el archivo y ese pasa
a la etapa siguiente, donde se formatea como enunciado para los estudiantes. Por eso
cada problema tiene que sostenerse solo, sin los otros dos y sin el resto de la
minuta.

No evalúas, no pones nota y no escribes nada en GitHub. Solo generas la minuta.

## Antes de empezar

Los repositorios ya tienen que estar descargados. Si `contexto.py` reclama que no
encuentra el manifiesto, detente y dile al usuario que corra primero:

```bash
cd assignment-assessment && python3 clone_repos.py --dest RUTA
```

## Argumentos que puede traer la invocación

| Argumento | Efecto |
|---|---|
| `--clones DIR` | Directorio de clones. Sin él se usa el de la última descarga. |
| `--group N` | Solo ese grupo. Repetible. Sin él, **todos** los del manifiesto. |
| `--schema SLUG` | Schema de sub-partes y puntaje. Sin él, `default`. |
| `--canonica RUTA --rama RAMA` | Solución canónica para el fallback. Si `course.toml` la declara, el manifiesto ya la trae y no hace falta pedirla. |
| `--base REF` | Rama o commit del código base dentro del repo canónico (por defecto, su commit inicial). |
| `--tarea NOMBRE` | Nombre de la tarea, que nombra el directorio de minutas. Sin él se usa el del manifiesto. |
| `--rehacer` | Regenera los `QUESTIONS.md` que ya existen. Sin él se saltan. |

Si la invocación viene en lenguaje natural («los primeros cinco grupos», «solo el
7»), traduce eso a la selección de grupos y díselo al usuario antes de partir.

## Procedimiento

`SCRIPT` es `.claude/skills/preguntas-revision/scripts/contexto.py` (ruta relativa a
la raíz del repositorio).

### 0. Carga el schema

```bash
python3 SCRIPT schema --slug default
```

Imprime el schema validado (el slug coincide con el nombre del archivo y las
sub-partes suman el total) y su texto completo: cuántas sub-partes tiene cada
problema, qué mide cada una, cuántos puntos vale y qué respuesta vale el puntaje
completo. **Léelo entero y síguelo al pie de la letra en los tres problemas.** Si el
script lo rechaza, detente y dile al usuario qué está mal; no inventes un schema ni
uses otro.

Los schemas viven en `.claude/skills/preguntas-revision/schemas/<slug>.md`. Para
saber cuáles hay: `python3 SCRIPT schema --listar`.

### 1. Ubica el trabajo

```bash
python3 SCRIPT listar [--clones DIR]
```

Te da el curso, el directorio de salida, la solución canónica declarada y una fila
por grupo: estado del clon, commits sobre el base, tamaño del diff, si el avance
alcanza y si ya existe su `QUESTIONS.md` (y si el docente ya marcó un problema).

Salta los grupos que ya tienen minuta, salvo que la invocación traiga `--rehacer`.
Salta también los que aparezcan con estado `error` o `sin clon`, y anótalos para el
resumen final.

Si vas a procesar **más de un grupo**, dile al usuario cuántos son antes de partir.

### 2. Para cada grupo, junta el contexto

```bash
python3 SCRIPT grupo [--clones DIR] --group N
```

Eso imprime, en una sola pasada: integrantes, rama y commit revisado, ruta del
enunciado, archivos tocados sobre el código base, el veredicto de avance y el diff
completo del código.

Lee el **enunciado** (el `README.md` de la raíz del clon, cuya ruta te dio el paso
anterior): sin saber qué se pedía no puedes distinguir lógica medular de andamiaje,
y lo vas a necesitar para **citar textualmente** los requisitos que toque cada
problema (ver el paso 4). Si el diff viene truncado y necesitas ver un archivo
entero, léelo con Read desde la ruta del clon, o pide un rango con
`git -C <clon> diff <base>..<head> -- <ruta>`.

### 3. Decide sobre qué preguntar

Busca las regiones donde está la **lógica que resuelve los objetivos del enunciado**:
el algoritmo, la máquina de estados, la consulta, la sincronización, la validación
de reglas de negocio, el manejo de concurrencia o de errores. Descarta imports,
getters, plantillas, estilos, archivos de configuración, código autogenerado y
cualquier cosa que el equipo docente ya entregaba en el base.

Selecciona **tres secciones** de código, una por problema, lo más distintas posible
entre sí: así los tres candidatos le dan al docente opciones reales y no tres
versiones de la misma pregunta. Si el trabajo del grupo es pequeño y no da para
tres secciones, dos problemas pueden mirar la misma sección desde ángulos
distintos (una decisión de diseño en uno, un borde de ejecución en otro); dilo en la
sección para el revisor. Una sección densa vale más que tres triviales.

**Cuándo caer en el fallback.** El veredicto del script cuenta líneas, no ideas:
confírmalo leyendo el diff. Usa la solución canónica cuando el grupo no dejó lógica
propia sobre la cual preguntar — repositorio en el código base, solo `README` o
configuración tocados, o cambios cosméticos. En ese caso:

```bash
python3 SCRIPT canonica --repo RUTA --branch RAMA [--base REF]
```

Toma los fragmentos medulares de la solución canónica y formula los problemas sobre
ellos con el mismo criterio y el mismo schema. La minuta debe decir, arriba y sin
ambigüedad, que los problemas son sobre la solución de referencia porque el grupo no
presentó avance suficiente.

Si no tienes con qué correr el fallback (no hay solución canónica en el manifiesto
ni en la invocación), no inventes código: escribe igual el `QUESTIONS.md` con la
sección de contexto, deja anotado que falta la solución canónica y pídesela al
usuario al final.

### 4. Escribe los tres problemas

Cada problema sigue el schema cargado en el paso 0: **las mismas sub-partes, en el
mismo orden, con los mismos puntos**, y la suma de puntos es el total del schema
(10 en `default`). El tipo y el puntaje de cada sub-parte van escritos en el texto
del problema, para que el estudiante sepa qué se le pide y cuánto vale.

Cada problema es **autocontenido**. El estudiante que lo responda **no tendrá a la
vista ni el enunciado de la tarea ni el código de su repositorio**; solo el texto del
problema. Por lo tanto:

- **Todo fragmento necesario va citado dentro del problema**, con su referencia
  `ruta/archivo.ext:desde-hasta` en la línea inmediatamente anterior al bloque de
  código y el bloque con su lenguaje, recortado a lo esencial (5 a 25 líneas). Si
  un problema cita dos fragmentos, cada uno lleva la suya. Sin esa referencia el
  ayudante no puede abrir el archivo mientras pregunta.
- **El fragmento se muestra dentro de su función.** Un trozo suelto de un loop no
  se entiende sin saber de qué función es. Usa `archivo --marco`, que imprime el
  rango con la firma de la función arriba, la llave de cierre abajo y `// ...`
  (o `# ...` en Python) donde se omitió código. Esas líneas no existen en el
  archivo: la referencia sigue siendo la del rango citado. Si el script no
  reconoce la función (código fuera de toda función, lenguaje sin soporte), cita el
  rango tal cual y, si hace falta, di en una frase dónde está.
- **Si el problema o una sub-parte aluden a un requisito del enunciado** («el
  quantum de nivel 1 es de 3 ticks», «`max == 0` debe retornar 0»), el requisito va
  **citado textualmente** dentro del problema, en un blockquote encabezado «Del
  enunciado de la tarea», copiado del `README.md` del clon. No escribas «como pide
  el enunciado» sin la cita. Esto vale para cualquier schema.
- **Si una sub-parte depende de algo del código base que no está en el fragmento**
  (una constante, la firma de una función que se llama, el comportamiento de una
  rutina del framework), dáselo al estudiante: un segundo fragmento con su
  referencia, o una frase que lo defina («`NPROC` es 64; `argptr` rechaza el rango
  si excede el tamaño del proceso»). Sácalo del código con `archivo`, no de memoria.
- **Ningún problema depende de otro**: nada de «la función del problema 1» ni «como
  vieron arriba». Si dos problemas necesitan el mismo fragmento, se cita en ambos.
- El texto va en español, en segunda persona plural (ustedes), tal como lo haría el
  ayudante, y es concreto y verificable: nada de «expliquen su arquitectura».
- **Cada sub-parte es una sola pregunta**, con un solo signo de interrogación o una
  sola consigna. El contexto (estado inicial, línea señalada, cambio hipotético) va
  antes, en forma declarativa. Las preguntas de seguimiento van a la sección para
  el revisor como repreguntas posibles; el schema detalla el criterio.
- Un problema se responde **solo si se entendió ese código**. Si se puede contestar
  leyendo el requisito citado, o con una generalidad de la asignatura, no sirve.

Para cada problema escribe también, en la sección **para el revisor**, la respuesta
esperada **de cada sub-parte**, qué respuesta vale el puntaje completo, qué vale
puntaje parcial (según los criterios del schema) y qué señales indican que el grupo
no escribió o no entiende ese código.

**Verifica los rangos de líneas.** No los estimes a partir del diff: los números
del encabezado `@@` no son los del archivo final. Sácalos de

```bash
python3 SCRIPT archivo --group N --ruta src/router.py --desde 11 --hasta 19
```

que imprime el archivo numerado **tal como está en el commit revisado** y te
devuelve la referencia ya formada para citar. Con `--marco` imprime en cambio el
rango enmarcado en su función, sin números y listo para pegar en el bloque de
código: es la forma normal de citar. Para la solución canónica, lo mismo con
`--repo RUTA --branch RAMA`.

**Verifica las simulaciones.** Una respuesta esperada equivocada arruina la
evaluación. Si el fragmento se puede ejecutar sin infraestructura —una función pura,
un módulo sin dependencias externas— corre tu caso de prueba y confirma el resultado
antes de escribirlo. Si no, reprodúcelo en un modelo mínimo (unas líneas de Python
que imiten exactamente la lógica del fragmento) o trázalo a mano y revisa dos veces.
No ejecutes código de alumnos que abra la red, escriba fuera de un directorio
temporal, pida credenciales o levante servicios.

Ejecuta siempre **sobre una copia en un directorio temporal** (el scratchpad de la
sesión sirve), nunca dentro del clon: correr el código ahí le deja archivos de
compilación y ensucia el clon que el ayudante va a abrir.

Nunca insinúes plagio ni pongas juicios sobre las personas: describes el código y
qué hay que saber para explicarlo. Si el código no implementa algo que el enunciado
pedía, puedes preguntar por lo que **sí** hace y consignar la ausencia como hecho en
la sección para el revisor; no la conviertas en pregunta trampa.

### 5. Guarda la minuta

En `<output_dir>/grupo-XX/QUESTIONS.md`, donde `output_dir` viene en el manifiesto
y `XX` es el número de grupo con dos dígitos. El manifiesto ya resuelve el anidado
por curso y por tarea:

```
assignment-assessment/output/<sigla-curso>/<tarea>/grupo-XX/QUESTIONS.md
```

Ese nivel de la tarea importa: el mismo curso usa la herramienta varias veces al
semestre y las minutas de la tarea 2 no pueden pisar las de la tarea 1. Si la
invocación trae `--tarea NOMBRE`, reemplaza ese nivel; si trae `--output DIR`, usa
ese directorio como raíz. Crea los directorios que falten.

Usa esta estructura. Las etiquetas `(a)`, `(b)`, `(c)`, sus tipos y sus puntos son
los del schema cargado; los de abajo corresponden a `default`:

````markdown
# Revisión de código — Grupo XX

- **Curso:** <nombre del curso>
- **Tarea:** <tarea del manifiesto>
- **Repositorio:** <repo> (<url>)
- **Commit revisado:** <sha corto> — <fecha> — «<asunto>»
- **Integrantes:** <nombre (@handle), …>
- **Ayudante:** <nombre>
- **Avance sobre el código base:** <n> commits, <n> archivos, +<n>/−<n> líneas
- **Schema:** `<slug>` — <total> puntos: (a) <n> · (b) <n> · (c) <n>

> (Solo en el fallback) El grupo no presenta avance suficiente para preguntar sobre
> su código: los problemas son sobre la solución de referencia.

## Selección para la evaluación

Marca con `[x]` el problema que pasa a la etapa siguiente. Solo uno.

- [ ] Problema 1 — <título corto>
- [ ] Problema 2 — <título corto>
- [ ] Problema 3 — <título corto>

## Qué pedía el enunciado

Dos o tres líneas, para el revisor, con los objetivos que tocan los problemas. Los
requisitos que cada problema necesita van citados dentro del problema, no acá.

## Problemas candidatos

### Problema 1 — <título corto>

**Fragmento:** `ruta/archivo.ext:120-148` — commit `<sha corto>`

```<lenguaje>
<fragmento, tal como aparece en esas líneas>
```

**Del enunciado de la tarea:**

> «<cita textual del requisito al que alude el problema>»

(Solo si el problema alude a un requisito. Si necesita más de un fragmento o una
definición del código base, van aquí también, cada uno con su referencia.)

**(a) Comprensión conceptual — 4 puntos.** <texto que dirá el ayudante>

**(b) Simulación de ejecución — 3 puntos.** <entrada o estado inicial concreto y
qué se pide seguir>

**(c) Detalle del código — 3 puntos.** <la línea o decisión concreta y la pregunta>

### Problema 2 — …

### Problema 3 — …

## Para el revisor

No se le muestra al grupo. Para cada problema y cada sub-parte: respuesta esperada,
qué vale el puntaje completo, qué vale puntaje parcial y señales de alerta. Cada
problema repite la referencia de su fragmento, para leerlo sin volver arriba.

### Problema 1 — `ruta/archivo.ext:120-148`

- **(a) · 4 pts.** Respuesta esperada: … Completo si … Mitad si … Señales: …
- **(b) · 3 pts.** Traza esperada: … (verificada con …). Completo si … Mitad si …
- **(c) · 3 pts.** …

### Problema 2 — …

### Problema 3 — …
````

### 6. Cierra

Cuando termines todos los grupos, informa en una tabla corta: grupo, schema usado,
si usó el fallback y dónde quedó el archivo. Menciona aparte los grupos saltados y
por qué (minuta ya existente, clon con error, sin solución canónica). Recuerda al
usuario que el paso siguiente es marcar con `[x]` un problema por grupo en la
sección «Selección para la evaluación» y luego correr la skill `preparar-iet`, que
convierte el problema marcado en el enunciado y la pauta del IET.

## Errores comunes

- **Preguntar sobre código del base.** Todo lo que preguntes tiene que estar en el
  diff del grupo (o en la solución canónica, si es fallback).
- **Aludir al enunciado sin citarlo.** «Como pide el enunciado» no le sirve a un
  estudiante que no lo tiene. La cita textual va dentro del problema.
- **Un problema que depende de otro.** Solo uno de los tres se va a usar; cada uno
  cita lo que necesita.
- **Sub-partes que no siguen el schema.** Mismo número, mismo orden, mismos puntos
  en los tres problemas; la suma es el total del schema.
- **Tres problemas sobre la misma sección.** Reparte entre las secciones elegidas
  para que la selección del docente sea una decisión real.
- **Preguntas que se responden con el requisito citado.** Pregunta por el código
  escrito, no por el problema planteado.
- **Citar un fragmento de 200 líneas.** Recorta al núcleo.
- **Inventar rutas o números de línea.** Sácalos de `archivo`, que lee el commit
  revisado, y comprueba que el fragmento citado sea el de ese rango.
- **Citar sin referencia.** Todo bloque de código lleva encima su
  `archivo:desde-hasta`.
- **Citar un trozo sin su función.** El estudiante necesita ver la firma para saber
  dónde está parado: `archivo --marco`.
- **Una simulación sin verificar.** La respuesta esperada de la sub-parte de
  ejecución se comprueba antes de escribirla.
- **Varias preguntas en una sub-parte.** «¿Qué cambiaría…? ¿Cuál de los dos…?» son
  dos preguntas: el estudiante responde en tiempo acotado. Deja una y lleva la otra
  al revisor.
