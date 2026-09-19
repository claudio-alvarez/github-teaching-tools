---
slug: default
nombre: Comprensión, simulación y detalle
puntos: 10
---

# Schema `default`

Tres sub-partes **graduadas por dificultad** sobre un mismo fragmento del código del
grupo (o dos fragmentos que trabajan juntos). Miden, en orden: si el estudiante
entiende qué hace el código que entregó su grupo, si puede seguir su ejecución, y si
conoce las decisiones concretas que tomó al escribirlo.

| Parte | Puntos | Tipo | Qué mide |
|---|---|---|---|
| a | 4 | comprensión conceptual | Describir con sus palabras qué hace el fragmento y por qué está construido así. |
| b | 3 | simulación de ejecución | Seguir el código paso a paso a partir de una entrada o un estado inicial concreto. |
| c | 3 | detalle del código | Justificar una decisión puntual: una llamada, sus argumentos, su orden, una condición. |

Las tres partes se responden **solo con el fragmento citado en el problema**: el
estudiante no tiene el enunciado de la tarea ni el resto de su repositorio a la
vista.

**Una sola pregunta por sub-parte.** El estudiante responde con lápiz y papel y en
tiempo acotado: cada sub-parte formula **una** pregunta, con **un** signo de
interrogación, y pide **una** cosa. Lo que haga falta para responderla (el estado
inicial, la línea a la que se apunta, el cambio hipotético) va como contexto
declarativo antes de la pregunta, no como preguntas adicionales. Si al escribir una
sub-parte aparecen dos preguntas, elige la que mejor discrimine y descarta la otra,
o muévela a la sección para el revisor como algo que el ayudante puede repreguntar.

| Así no | Así sí |
|---|---|
| «¿Qué cambiaría si movieran el boost después de la contabilidad? ¿Cuál de los dos órdenes alcanza al proceso que corre?» | «El bloque del boost está antes del de contabilidad. Si lo movieran después, ¿en qué nivel terminaría este tick el proceso que está corriendo?» |
| «Expliquen qué representa el cursor, por qué parte en `+1` y qué garantiza guardarlo solo al elegir. ¿Cómo se logra la prioridad estricta?» | «Expliquen qué información conserva `cursor_low` entre una selección y la siguiente, y cómo `cursor_low + 1 + i` la usa para dar el turno.» |

## Parte (a) — comprensión conceptual · 4 puntos

Pide una **descripción conceptual** del fragmento: qué problema resuelve, cuál es la
idea que lo organiza, qué propiedad conserva entre una ejecución y la siguiente o qué garantiza a quien lo llama. Es
la parte más accesible: quien escribió o revisó ese código la contesta sin dudar.

- Pregunta por la idea, no por la sintaxis: «expliquen qué representa el cursor y
  qué garantiza moverlo solo cuando se agota el quantum», no «¿qué hace la línea
  12?».
- Es una sola consigna, amplia pero única: «expliquen cómo X logra Y». La respuesta
  esperada puede tener varios elementos (la idea, la variable que la sostiene, la
  rama que la aplica) y el reparto de los 4 puntos entre esos elementos va en la
  sección para el revisor, no como incisos en la pregunta.
- No se contesta con una generalidad de la asignatura («es un scheduler MLFQ»): la
  respuesta tiene que mencionar elementos que solo están en ese código.
- Evita términos que el estudiante puede no haber visto todavía, como «invariante»:
  pregunta «qué garantiza», «qué información conserva» o «qué se mantiene cierto
  entre una decisión y la siguiente». El vocabulario del enunciado y del código es
  el límite.

**Puntaje completo:** la explicación identifica la idea central y la conecta con la
estructura del código (qué variable la sostiene, qué rama la aplica). **Mitad:**
describe correctamente lo que hace pero no por qué está construido así. **Cero:**
parafrasea el código línea a línea sin decir qué logra, o describe otro algoritmo.

## Parte (b) — simulación de ejecución · 3 puntos

Fija una **entrada o un estado inicial concreto** y pide seguir el código: qué valor
toma cada variable relevante, por qué rama entra, qué retorna, en qué orden ocurren
las cosas. Elige un caso que revele una decisión del código, no el camino feliz
trivial: un borde (lista vacía, dos candidatos de igual costo, contador que llega al
límite justo ese tick), o una interacción entre dos partes del fragmento.

- Da todos los datos iniciales en el texto: valores, índices, estados, constantes
  del código base que el fragmento usa y que no aparecen en él.
- Pide **una** traza acotada (de 4 a 10 pasos) con un resultado final concreto: «¿en
  qué nivel y con qué `slice_ticks` termina P?». Las preguntas de seguimiento («¿y
  por qué no es A el primero?») van al revisor como repreguntas, no al enunciado.
- La respuesta esperada tiene que estar **verificada** antes de escribirla: ejecuta
  el fragmento en un directorio temporal si es una función pura; si no, trázalo a
  mano y revisa dos veces.

**Puntaje completo:** la traza es correcta en el orden y en los valores finales.
**Mitad:** el orden es correcto pero se equivoca en un valor, o llega al resultado
correcto sin poder justificar un paso. **Cero:** la traza sigue un comportamiento
que el código no tiene.

## Parte (c) — detalle del código · 3 puntos

Pregunta por **algo específico y verificable** del fragmento: por qué llaman a esa
función y no a otra, qué parámetros le pasan y por qué esos, por qué ese orden entre
dos sentencias, qué pasaría si la llamada estuviera en otro lugar o si faltara una
condición. Es la parte que mejor distingue a quien escribió el código de quien solo
lo leyó.

- Apunta a una línea o dos, nombradas en el texto («la llamada a `copyout` de la
  línea 628», «el `else` que sigue al boost»).
- Formula el «qué pasaría si» con **un** cambio concreto y **una** consecuencia
  pedida: mover una línea, cambiar un argumento, sacar una guarda, y qué valor o
  estado cambia. Evita el hipotético abierto («¿se podría hacer mejor?») y evita
  encadenar «¿y qué pasaría además con…?».
- La respuesta correcta se deduce del fragmento y de lo que el problema aporta del
  código base; no depende de leer otros archivos.

**Puntaje completo:** explica la decisión y sus consecuencias con precisión
(qué se rompe, en qué caso). **Mitad:** identifica para qué sirve la línea pero no
qué pasaría sin ella o con el cambio propuesto. **Cero:** atribuye a la línea un
efecto que no tiene.
