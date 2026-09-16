---
name: preguntas-revision
description: Genera la minuta de preguntas de revisión de código (QUESTIONS.md) para cada grupo de un curso, a partir de los repositorios ya descargados con assignment-assessment/clone_repos.py. Úsala cuando el usuario pida preguntas de revisión, interrogar a los grupos sobre su código, preparar la revisión presencial de una tarea o entrevistas de código. Se activa con "preguntas de revisión", "minutas de los grupos", "QUESTIONS.md", "revisar las entregas del grupo N", "preguntas para la entrevista de código".
---

# Preguntas de revisión de código por grupo

Produces, para cada grupo, un `QUESTIONS.md` con **tres preguntas** que el ayudante
le hará al grupo sobre el código que entregó. Las preguntas se anclan a fragmentos
concretos del repositorio y sirven para distinguir a quien entiende lo que entregó
de quien no.

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
| `--canonica RUTA --rama RAMA` | Solución canónica para el fallback. Si `course.toml` la declara, el manifiesto ya la trae y no hace falta pedirla. |
| `--base REF` | Rama o commit del código base dentro del repo canónico (por defecto, su commit inicial). |
| `--tarea NOMBRE` | Nombre de la tarea, que nombra el directorio de minutas. Sin él se usa el del manifiesto. |
| `--rehacer` | Regenera los `QUESTIONS.md` que ya existen. Sin él se saltan. |

## Procedimiento

`SCRIPT` es `.claude/skills/preguntas-revision/scripts/contexto.py` (ruta relativa a
la raíz del repositorio).

### 1. Ubica el trabajo

```bash
python3 SCRIPT listar [--clones DIR]
```

Te da el curso, el directorio de salida, la solución canónica declarada y una fila
por grupo: estado del clon, commits sobre el base, tamaño del diff, si el avance
alcanza y si ya existe su `QUESTIONS.md`.

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
anterior): sin saber qué se pedía no puedes distinguir lógica medular de andamiaje.
Si el diff viene truncado y necesitas ver un archivo entero, léelo con Read desde
la ruta del clon, o pide un rango con `git -C <clon> diff <base>..<head> -- <ruta>`.

### 3. Decide sobre qué preguntar

Busca las regiones donde está la **lógica que resuelve los objetivos del enunciado**:
el algoritmo, la máquina de estados, la consulta, la sincronización, la validación
de reglas de negocio, el manejo de concurrencia o de errores. Descarta imports,
getters, plantillas, estilos, archivos de configuración, código autogenerado y
cualquier cosa que el equipo docente ya entregaba en el base.

Selecciona **de una a tres secciones** de código. Una sola sección densa es mejor
que tres triviales.

**Cuándo caer en el fallback.** El veredicto del script cuenta líneas, no ideas:
confírmalo leyendo el diff. Usa la solución canónica cuando el grupo no dejó lógica
propia sobre la cual preguntar — repositorio en el código base, solo `README` o
configuración tocados, o cambios cosméticos. En ese caso:

```bash
python3 SCRIPT canonica --repo RUTA --branch RAMA [--base REF]
```

Toma los fragmentos medulares de la solución canónica y formula las preguntas sobre
ellos con el mismo criterio. La minuta debe decir, arriba y sin ambigüedad, que las
preguntas son sobre la solución de referencia porque el grupo no presentó avance
suficiente.

Si no tienes con qué correr el fallback (no hay solución canónica en el manifiesto
ni en la invocación), no inventes código: escribe igual el `QUESTIONS.md` con la
sección de contexto, deja anotado que falta la solución canónica y pídesela al
usuario al final.

### 4. Escribe las tres preguntas

Tres preguntas en total por grupo, de estos dos tipos:

1. **Explicación algorítmica** — qué hace este código y por qué así: la idea detrás
   de la estructura elegida, el invariante que mantiene, el costo, qué se rompe si
   se cambia tal decisión.
2. **Simulación de ejecución** — dada una entrada concreta que tú fijas, qué ocurre
   paso a paso: qué valor toma cada variable relevante, por qué rama entra, qué
   devuelve, qué pasa con un caso borde (lista vacía, dos caminos de igual costo,
   token vencido, colisión de escritura).

Incluye **al menos una de cada tipo**. La tercera es la que mejor le calce al código
de ese grupo.

Cada pregunta:

- Lleva **pegada al fragmento citado la referencia de dónde salió**: ruta del
  archivo dentro del repositorio y rango de líneas, como
  `src/router.py:120-148`, en la línea inmediatamente anterior al bloque de
  código. Si una pregunta cita dos fragmentos, cada uno lleva la suya. Sin esa
  referencia el ayudante no puede abrir el archivo mientras pregunta.
- Cita el fragmento en un bloque de código con su lenguaje, recortado a lo
  esencial (5 a 25 líneas).
- Se responde **solo si se entendió ese código**. Si se puede contestar leyendo el
  enunciado, o con una generalidad de la asignatura, no sirve.
- Es concreta y verificable: nada de "explique su arquitectura".
- Va en español, en segunda persona plural (ustedes), tal como la haría el ayudante.

Para cada pregunta escribe también, en una sección aparte marcada **para el
revisor**, qué respuesta se espera escuchar y qué señales indican que el grupo no
escribió o no entiende ese código.

**Verifica los rangos de líneas.** No los estimes a partir del diff: los números
del encabezado `@@` no son los del archivo final. Sácalos de

```bash
python3 SCRIPT archivo --group N --ruta src/router.py --desde 11 --hasta 19
```

que imprime el archivo numerado **tal como está en el commit revisado** y te
devuelve la referencia ya formada para citar. Para la solución canónica, lo mismo
con `--repo RUTA --branch RAMA`. Copia el fragmento de esa salida, sin los números
de línea.

**Verifica las simulaciones.** Una respuesta esperada equivocada arruina la
revisión. Si el fragmento se puede ejecutar sin infraestructura —una función pura,
un módulo sin dependencias externas— corre tu caso de prueba y confirma el resultado
antes de escribirlo. No ejecutes código de alumnos que abra la red, escriba fuera de
un directorio temporal, pida credenciales o levante servicios: en ese caso traza la
ejecución a mano y revisa dos veces.

Ejecuta siempre **sobre una copia en un directorio temporal**, nunca dentro del
clon: correr el código ahí le deja archivos de compilación y ensucia el clon que el
ayudante va a abrir.

Nunca insinúes plagio ni pongas juicios sobre las personas: describes el código y
qué hay que saber para explicarlo.

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

Usa esta estructura:

````markdown
# Revisión de código — Grupo XX

- **Curso:** <nombre del curso>
- **Tarea:** <tarea del manifiesto>
- **Repositorio:** <repo> (<url>)
- **Commit revisado:** <sha corto> — <fecha> — «<asunto>»
- **Integrantes:** <nombre (@handle), …>
- **Ayudante:** <nombre>
- **Avance sobre el código base:** <n> commits, <n> archivos, +<n>/−<n> líneas

> (Solo en el fallback) El grupo no presenta avance suficiente para preguntar sobre
> su código: las preguntas son sobre la solución de referencia.

## Qué pedía el enunciado

Dos o tres líneas con los objetivos que tocan las preguntas.

## Preguntas

### 1. <título corto> — <explicación algorítmica | simulación de ejecución>

**Fragmento:** `ruta/archivo.ext:120-148` — commit `<sha corto>`

```<lenguaje>
<fragmento, tal como aparece en esas líneas>
```

**Pregunta.** <texto que dirá el ayudante>

### 2. …
### 3. …

## Para el revisor

Respuesta esperada y señales de alerta de cada pregunta. No se le muestra al grupo.
Cada entrada repite la referencia del fragmento, para poder leerla sin volver arriba.

1. **<título> — `ruta/archivo.ext:120-148`.** …
2. …
3. …
````

### 6. Cierra

Cuando termines todos los grupos, informa en una tabla corta: grupo, cuántas
preguntas, si usó el fallback y dónde quedó el archivo. Menciona aparte los grupos
saltados y por qué (minuta ya existente, clon con error, sin solución canónica).

## Errores comunes

- **Preguntar sobre código del base.** Todo lo que preguntes tiene que estar en el
  diff del grupo (o en la solución canónica, si es fallback).
- **Preguntas que se responden con el enunciado.** Pregunta por el código escrito,
  no por el problema planteado.
- **Tres preguntas sobre el mismo `if`.** Reparte entre las secciones elegidas.
- **Citar un fragmento de 200 líneas.** Recorta al núcleo.
- **Inventar rutas o números de línea.** Sácalos de `archivo`, que lee el commit
  revisado, y comprueba que el fragmento citado sea el de ese rango.
- **Citar sin referencia.** Todo bloque de código lleva encima su
  `archivo:desde-hasta`.
