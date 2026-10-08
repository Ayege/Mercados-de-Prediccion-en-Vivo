# Noticias, encuadre y opinión

En internet hay miles de noticias sobre cualquier hecho, y la opinión se mueve
según cómo están escritas y según qué medios lee cada quien. A los modelos les
pasa lo mismo: leen esas noticias. Esta parte de la demo lo muestra en cuatro
piezas, de la más real a la más simulada:

1. [La sala, dividida al azar](#1-la-sala-dividida-al-azar): dos titulares sobre
   el mismo hecho, y cada persona ve uno.
2. [El oráculo, puesto a prueba con los titulares](#2-el-oráculo-puesto-a-prueba-con-los-titulares):
   el veredicto no puede depender de la redacción.
3. [Agentes con dieta de medios](#3-agentes-con-dieta-de-medios): preguntas que
   nacen de las noticias del día y cuatro agentes que leen solo izquierda, solo
   derecha, ambas o ninguna.
4. [Credulidad en el laboratorio](#4-credulidad-en-el-laboratorio-simulado):
   agentes simulados que creen o no noticias alarmistas.

La regla que atraviesa todo: **ningún titular de un medio real lo escribe el
modelo, y ninguna inclinación política la decide el código.**

## 1. La sala, dividida al azar

Una pregunta con encuadre lleva dos titulares sobre el mismo hecho: uno empuja
hacia el SÍ y otro hacia el NO. Cada persona ve solo uno, encima de la pregunta,
en su móvil.

- **Asignación.** Aleatorización en bloques: el grupo más chico recibe a la
  siguiente persona y, si están empatados, decide un hash del nombre. Los grupos
  nunca se separan por más de una persona, y nadie elige su grupo.
- **Qué se mide.** Por grupo: cuántas personas vieron el titular, cuántas
  apostaron y qué parte del dinero fue al SÍ. Solo agregados, nunca quién vio
  qué.
- **Qué ve la proyección.** Los dos grupos y su diferencia, en vivo. Los
  titulares quedan **ocultos** hasta que el ponente pulsa «Revelar titulares» o
  hasta que se resuelve: la proyección la ve toda la sala, y mostrarlos antes
  arruinaría el experimento.

Como la asignación es al azar, en esa sala la diferencia entre grupos la causó
el titular y no quién es cada grupo. Las otras preguntas solo muestran
correlación. Con ochenta personas puede ser ruido, y la proyección lo dice.

### Crear una pregunta con encuadre

Los titulares del juego `encuadre` son **titulares de ensayo**: los escribió el
proyecto y la pantalla los marca así. Antes de una charla, cámbialos por
titulares reales con su enlace (`https` obligatorio). Nunca atribuyas a un medio
un titular que no publicó.

```bash
curl -X POST $URL/api/markets -H "X-Presenter-Key: $PRESENTER_KEY" -H 'Content-Type: application/json' -d '{
  "question": "¿Se publicó Python 3.15.0 (versión final) antes del 15 de octubre de 2026?",
  "criteria": "SÍ si python.org muestra la release 3.15.0 final con fecha igual o anterior al 15/10/2026.",
  "framing": {
    "pro_si": {"text": "…", "source": "Medio A", "url": "https://…"},
    "pro_no": {"text": "…", "source": "Medio B", "url": "https://…"}
  }
}'
```

## 2. El oráculo, puesto a prueba con los titulares

En una pregunta con encuadre, «Consultar al oráculo» hace tres consultas: sin
titular, con el pro-SÍ y con el pro-NO. `FramingPolicy` acepta el veredicto solo
si las tres coinciden. Si el modelo cambia de opinión con el titular, queda SIN
RESOLVER, porque los hechos eran los mismos.

- El titular llega al modelo como **dato no confiable**, dentro de `<noticia>`,
  y el prompt le dice que su tono no es evidencia.
- El fallo `noticia_como_verdad` enseña el error típico de un sistema que usa
  un LLM: sube la noticia a instrucción de sistema como «noticia verificada». El
  oráculo simulado la cree y responde hacia donde empuja; la política lo detecta.
- Si la consulta neutral no decide, no se gastan las otras dos.

Es el mismo patrón del resto del proyecto, *el modelo propone, el código
dispone*, aplicado a la manipulación por redacción.

## 3. Agentes con dieta de medios

Estas preguntas no son fijas: nacen de las noticias del día. En la proyección,
el ponente escribe un tema en «Pregunta desde las noticias».

1. **Búsqueda en Google News.** El servidor busca el tema en el RSS de Google
   News, una vez por lado, solo en los medios de la lista (`site:`) y en los
   últimos 7 días. Google News atribuye cada titular a su medio; uno de un medio
   que no está en la lista se descarta. Las ediciones en español cuentan como su
   medio: cnnespanol.cnn.com es CNN.
2. **El editor (Gemini, sin buscar)** recibe esos titulares numerados en dos
   grupos, A y B, sin saber cuál es izquierda y cuál derecha. Propone una
   pregunta de sí o no, verificable, sobre un asunto que cubran los dos grupos.
   Para citar un titular solo puede dar su número: no puede escribirlo ni
   cambiarlo.
3. **`NewsPolicy` decide si el borrador sirve.** Pide una pregunta de sí o no,
   un criterio, un tipo y al menos un titular de cada lado. Si falta algo, el
   borrador queda rechazado con su traza y se busca otra vez.
4. **El ponente abre la pregunta.** La sala apuesta como en cualquier otra.
5. **«Que opinen los agentes».** Cuatro agentes Gemini leen la misma cobertura,
   cada uno solo lo que su dieta permite: solo izquierda, solo derecha, ambas o
   ninguna. No buscan en internet. Cada uno estima P(SÍ) y compra hasta llevar el
   precio a su creencia, con un tope de 200 créditos (`AGENTES_PRESUPUESTO`). La
   proyección muestra qué leyó cada uno, qué creyó, contra qué precio y cuánto
   apostó.
6. **Al resolver**, la misma tarjeta dice qué dieta ganó dinero y cuál perdió.

| Paso | Tiempo | Llamadas a Gemini |
| --- | --- | --- |
| Búsqueda y borrador | 10 s a 1 min (9 s medido en producción) | 1, como máximo una búsqueda cada 30 s |
| Opinión de los agentes | unos 30 s, en paralelo | 4, una sola vez por pregunta |

### Lo que enseña, y lo que no

- **Enseña** que, con los mismos hechos disponibles, la dieta de medios puede
  separar creencias, y que quien apuesta mueve el precio que ve la sala.
- **Los agentes apuestan en orden**, así que el último fija el precio. La
  pantalla lo dice.
- **Un LLM no es una hoja en blanco.** En la primera prueba real (inmigración,
  octubre de 2026) las cuatro dietas creyeron entre 80 y 88 %: el agente que no
  leyó nada respondió con lo que ya sabía. La dieta mueve a los agentes en
  algunos temas y casi nada en otros. Ensaya temas antes de la charla.

### La lista de medios

La inclinación de cada medio vive en [`app/medios.json`](../app/medios.json), o
en otro archivo indicado con `MEDIOS_ARCHIVO`. Ni el código ni el modelo
clasifican medios: cada entrada cita una fuente publicada y la proyección la
muestra.

| Lado | Medios | Fuente |
| --- | --- | --- |
| Izquierda | laSexta | Masip, Suau y Ruiz-Caballero (2020), *Profesional de la información* 29(5): la ciudadanía de izquierda confía en ella significativamente más |
| Izquierda | Público, infoLibre | CIS, *Estudio sobre audiencias de medios de comunicación social* (noviembre de 2023): la ciudadanía los ubica a la izquierda |
| Izquierda | CNN, The New York Times (Lean Left), The Guardian (Left) | AllSides Media Bias Chart (2024) |
| Derecha | ABC, El Mundo, La Razón, OKDiario | Masip et al. (2020): la ciudadanía de derecha confía en ellos significativamente más |
| Derecha | Fox News (Right), New York Post (Lean Right) | AllSides Media Bias Chart (2024) |

- **Es binaria:** «izquierda» incluye la centroizquierda y «derecha», la
  centroderecha.
- **Mide percepción de las audiencias**, no exactitud ni calidad periodística.
- **Quedan fuera** los medios que esas fuentes ubican como punto de equilibrio
  (El País, TVE) o al centro (WSJ), y los que no tienen una clasificación
  publicada que se pueda citar, entre ellos los dominicanos.
- **Para añadir un medio**, inclúyelo con la fuente de su clasificación. Hace
  falta al menos uno de cada lado; con la lista vacía, la búsqueda se niega a
  correr. Cambiar la lista exige publicar una imagen nueva.

```json
{
  "fuente": "Quién definió la lista y con qué criterio",
  "medios": [
    {"nombre": "Medio A", "dominio": "medio-a.com", "inclinacion": "izquierda", "fuente": "…"},
    {"nombre": "Medio B", "dominio": "medio-b.com", "inclinacion": "derecha", "fuente": "…"}
  ]
}
```

En ensayo (sin Vertex AI) se usan siempre dos medios **ficticios**, con dominios
`.example` y titulares marcados `[Ensayo]`. El editor simulado nunca pone
palabras en boca de un medio real.

## 4. Credulidad en el laboratorio (simulado)

Los agentes del laboratorio de [la nube](NUBE.md) tienen un gen `credulidad`.
Cada 10 ticks llega una noticia alarmista («se viene un pico») que acierta el
30 % de las veces. Mientras está fresca, cada agente infla su previsión según su
credulidad: enciende capacidad y sube precios antes de ver los datos. El ponente
puede publicar un **rumor alarmista** falso con un botón. La evolución decide si
creer paga, y la sala apuesta: «¿al cerrar la generación 5, los agentes serán
menos crédulos que al empezar?».

Lo que enseña sin que nadie lo programe: no hay una respuesta fija. En 20
semillas, la credulidad bajó en 9 y subió en 11. Un rumor que todos creen a
veces sube los precios y a veces los baja, porque los crédulos también encienden
más capacidad. Es un parámetro, no un modelo de opinión pública, y la tarjeta lo
dice.
