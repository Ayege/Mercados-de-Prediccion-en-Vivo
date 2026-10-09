# Oráculo

¿Cómo influyen los medios en lo que cree la gente y en lo que concluye una IA?
Oráculo lo pone a prueba en vivo. Las personas de una sala apuestan desde el
móvil si algo pasará o no, y la barra muestra la probabilidad que le da la sala
en conjunto. Unos agentes de IA leen las mismas noticias y también apuestan. Al
final, un modelo de IA busca la respuesta y el código decide si acepta lo que
dice. Todo corre en Google Cloud.

**Demo:** https://oraculo-api-346171942822.us-east1.run.app

La regla que atraviesa el proyecto: **el modelo propone, el código dispone.** Un
LLM es un componente no confiable, y lo interesante es ver dónde y por qué el
código le dice que no.

## Medios, gente e IA

Las personas y los modelos aprenden del mismo lugar: las noticias. Oráculo pone
a las dos frente al mismo hecho contado de formas distintas y mide cuánto se
mueve cada una.

| Qué se pregunta | Cómo se mide | Qué se ve en la proyección |
| --- | --- | --- |
| ¿Un titular cambia lo que cree **la gente**? | La sala se divide al azar en dos grupos. Cada grupo lee un titular distinto sobre el mismo hecho y apuesta. Como el reparto es al azar, la diferencia entre grupos la causa el titular, no quién es cada grupo | Qué parte de lo apostado por cada grupo fue al SÍ, y la diferencia en puntos |
| ¿Lo que lee **la gente** cambia lo que cree? | En las preguntas que nacen de las noticias, la sala se divide al azar: una mitad ve en su móvil solo los titulares de medios de izquierda y la otra, solo los de derecha | Qué parte de lo apostado por cada mitad fue al SÍ, junto a lo que creyó el bot que leyó lo mismo |
| ¿Un titular cambia lo que concluye **la IA**? | El oráculo responde tres veces: sin titular, con el que empuja al SÍ y con el que empuja al NO. Si su respuesta cambia con la redacción, el código la rechaza, porque los hechos eran los mismos | Las tres respuestas y si se aceptó el veredicto |
| ¿Lo que lee una IA cambia lo que **cree**? | Cuatro agentes Gemini reciben la cobertura del día filtrada por su dieta: solo medios de izquierda, solo de derecha, de ambos lados o ninguno. Cada uno da una probabilidad y apuesta | Qué titulares leyó cada agente, qué probabilidad le dio al SÍ y cuánto apostó |

La inclinación de cada medio no la decide el código ni el modelo: viene de
fuentes publicadas, citadas en pantalla. Los titulares son reales, de Google
News, y nunca los escribe el modelo.

### Cómo leer un resultado

- **Con una sala, una diferencia chica puede ser ruido.** Con pocas decenas de
  personas, unos puntos entre grupos no prueban nada. La pantalla lo dice.
- **Un LLM no es una hoja en blanco.** Trae lo que aprendió al entrenarse. En
  una prueba sobre inmigración, las cuatro dietas creyeron entre 80 y 88 %. En
  otra, sobre el Nobel de la Paz 2026, los agentes que leyeron noticias de
  cualquier lado creyeron entre 75 y 80 %. El agente sin noticias creyó 2 %
  porque no sabía que la premiada ya había ganado. A veces los medios mueven la
  opinión de la IA, y a veces solo le dan los hechos.
- **El orden importa.** Los agentes apuestan uno tras otro y el último deja la
  barra donde él cree. La pantalla lo dice.
- **Izquierda y derecha es una simplificación.** La lista es binaria y mide cómo
  perciben las audiencias a cada medio, no su calidad.

Así se comparan directamente: la mitad de la sala que leyó izquierda junto al
bot que leyó izquierda, y lo mismo con derecha. Los titulares y el razonamiento
de los bots no salen en la proyección hasta revelarlos, para no contaminar a la
otra mitad.

### Lo que todavía no mide

- **Las preguntas con un titular a favor y otro en contra** se crean por API con
  titulares reales y su enlace, sin un botón en la proyección.
- **Los bots apuestan en el mismo mercado que la sala**, así que la barra que
  ven las dos mitades ya incluye lo que apostaron los bots. La comparación limpia
  es la de qué apostó cada mitad, no la barra.

Los detalles de cada pieza están en [Noticias, encuadre y opinión](docs/NOTICIAS.md).

## La nube negocia sus recursos con el tráfico

Los móviles de la sala son la demanda real: cada consulta que hace un móvil que
entró a la sala cuenta como tráfico. Cada 10 s, la nube hace dos cosas con ese
tráfico, y la proyección muestra las dos en la sección «La nube negocia sus
recursos con su tráfico».

**1. Del tráfico a las máquinas (autoescalado predictivo).** La proyección lo
muestra como una cadena de cinco cifras y una gráfica:

| Paso | Qué pasa |
| --- | --- |
| Tráfico de la sala | Se miden las peticiones por segundo del último ciclo |
| Predicción | Un modelo de Holt (nivel y tendencia) predice las de los próximos 10 s. La gráfica pone lo real junto a lo que predijo un ciclo antes |
| Máquinas que pide | Una instancia mínima de Cloud Run por cada 10 req/s previstas (`INFRA_RPS_POR_INSTANCIA`), encendida **antes** de que llegue el tráfico para evitar arranques en frío |
| Máquinas que permite la política | `ActuationPolicy` recorta lo pedido a lo que la cuenta permite: 2 instancias mínimas en total, regiones permitidas y un cambio por minuto por región. Si recorta, la pantalla lo dice |
| Encendidas en Cloud Run | Lo que de verdad hay encendido, por región, y la última decisión: ejecutada o bloqueada, con su motivo |

**2. Quién atiende ese tráfico (la subasta).** El tráfico del ciclo, hasta 12
peticiones, se subasta entre cuatro agentes. Cada agente opera su propio servicio
de Cloud Run en una región distinta. Venden los que piden menos, cobran solo lo
que atienden a tiempo y pagan el costo real de Cloud Run, con precios del
catálogo de Cloud Billing. Cada 6 subastas se ofrece un contrato que exige dos
regiones (una coalición). Cada 12, la evolución copia a los agentes que más
ganaron, incluido si les conviene pagar una instancia siempre encendida.

Lo que esto es y lo que no:

- **Es real:** el tráfico, las instancias, los servicios de los agentes y sus
  costos, en Cloud Run. Una hora de mercado cuesta alrededor de un centavo.
- **Es pequeño a propósito:** con el tráfico de una sala y un tope de 2
  instancias, el escalado se nota en unidades, no en cientos.
- **No es descentralizado:** hay un subastador central y el dinero de los
  agentes es contable. Los detalles, en [La nube autónoma](docs/NUBE.md).

Para verlo, quien modera pulsa «Arrancar la nube» en la proyección y la sala abre
la página en el móvil. Si nadie mira la proyección ni `/nube.html` durante 30
minutos, la vigilia borra los servicios.

## Qué hace

| Parte | Qué pasa | Más |
| --- | --- | --- |
| **Creencia contra evidencia** | La sala apuesta sobre preguntas que nadie sabe con certeza. Gemini busca evidencia en la web y una política en código acepta o rechaza su veredicto. Los rechazos se pueden provocar a propósito para verlos | [Tipos de pregunta](docs/PREGUNTAS.md) |
| **Noticias y opinión** | La sala se divide al azar y cada mitad lee un titular distinto sobre el mismo hecho. Las preguntas también pueden nacer de las noticias del día, con cuatro agentes que solo leen medios de izquierda, solo de derecha, ambos o ninguno, y apuestan en el mismo mercado | [Noticias, encuadre y opinión](docs/NOTICIAS.md) |
| **Nube autónoma** | Bucles que actúan sobre Cloud Run de verdad: despliegan la topología que propone un modelo, escalan con el tráfico de los móviles, reparan fallas reales y tienen un mercado de agentes con precios reales. En local, un laboratorio simulado muestra lo mismo a cámara rápida | [La nube autónoma](docs/NUBE.md) |

Hay tres pantallas:

| Pantalla | Quién la ve | Para qué |
| --- | --- | --- |
| `/` | Cada persona, en su móvil | Entrar con el código de sala, apostar y responder el censo |
| `/proyeccion.html` | Todos, en una pantalla compartida | Ver los mercados, el código de sala y el mercado real de la nube; quien modera consulta al oráculo, crea preguntas desde las noticias y arranca o apaga la nube |
| `/nube.html` | Quien modera | Todos los detalles de la nube: topologías, nodos, fallas reales y la política de actuación |

Los controles de moderación aparecen solo si la URL termina en `#clave=…`.

## Probarlo en cinco minutos

Requiere Python 3.12 o superior. Sin credenciales de Google Cloud, todo corre en
modo de ensayo: oráculo simulado, medios ficticios y nada que cobre. **En
producción no hay nada simulado:** la API no arranca si el oráculo, las noticias,
la infraestructura o las preguntas no son reales.

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install --require-hashes -r requirements-dev.lock   # versiones fijadas y verificadas por hash
pre-commit install                     # controles de seguridad antes de cada commit
cp .env.example .env

pytest -q
uvicorn app.main:app --reload --port 8080
```

Abre la proyección en http://localhost:8080/proyeccion.html: ahí aparece el
código de sala. Con ese código, entra desde http://localhost:8080 (o desde otra
pestaña). La nube está en http://localhost:8080/nube.html. Más formas de
ensayar, incluida la infraestructura simulada, en
[CODIGO.md](docs/CODIGO.md#ensayar-sin-tocar-la-nube).

## Documentación

| Documento | Qué tiene |
| --- | --- |
| [Tipos de pregunta](docs/PREGUNTAS.md) | Qué mide cada tipo de pregunta, los juegos de preguntas (`SEED_SET`) y los fallos del oráculo que se pueden provocar |
| [Noticias, encuadre y opinión](docs/NOTICIAS.md) | El experimento de los dos titulares, la prueba del oráculo, los agentes con dieta de medios y la lista de medios con sus fuentes |
| [La nube autónoma](docs/NUBE.md) | Qué es real y qué es laboratorio, las dos compuertas y el mercado real con números medidos |
| [El código](docs/CODIGO.md) | Capas, estructura, tests, cómo ensayar y las decisiones de diseño |
| [Arquitectura](docs/ARQUITECTURA.md) | Diagramas C4, secuencias y fronteras de confianza |
| [Despliegue](docs/DESPLIEGUE.md) | Costos, permisos, primer despliegue, publicar cambios y limpieza |
| [Seguridad](SECURITY.md) | Modelo de amenazas, cada control con el test que lo fija y los riesgos aceptados |

## Cómo está hecho, en corto

- **Arquitectura limpia.** El dominio (mercado LMSR, políticas, agentes) no
  importa nada de I/O. Vertex AI, Cloud Run, Google News y la memoria son
  adaptadores detrás de puertos. Un test hace cumplir la regla de dependencias.
- **Fail-closed.** Ante un error de red, una respuesta ilegible, poca confianza
  o pocas fuentes, el veredicto queda SIN RESOLVER y el mercado sigue abierto.
- **Nada inventado sobre terceros.** Los titulares de medios reales vienen de
  Google News, nunca del texto del modelo. La inclinación de cada medio cita una
  fuente publicada. Lo simulado dice que es simulado.
- **Costo acotado.** Sin procesos en segundo plano, con escala a cero, topes en
  código, una vigilia que borra lo olvidado y un presupuesto de 10 USD al mes.
  Una hora de mercado real cuesta alrededor de un centavo.
- **Seguridad en cada paso.** Código de sala para entrar, clave de moderación en
  Secret Manager, CSP estricta, identidades con permisos mínimos (también para el
  pipeline), dependencias e imágenes fijadas por hash, y un pipeline que corre
  gitleaks, bandit, pip-audit, la suite completa y Trivy antes de publicar.

![Diagrama de contexto](docs/c4-nivel1-contexto.png)

## Ya resuelto

- Cada push a `master` publica a través del pipeline: un trigger de Cloud Build
  conectado al repositorio de GitHub.
- La sala sobrevive a que la API escale a cero: una foto firmada del estado en
  Cloud Storage (ver [Despliegue](docs/DESPLIEGUE.md#el-estado-sobrevive-a-la-escala-a-cero)).
- Una pregunta de cooperación que resuelve el mercado real (4 agentes), además de
  la simulada.
