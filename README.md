# Oráculo — mercado de predicción en vivo

Demo para charla. La audiencia opera un mercado de predicción desde el móvil y
los precios son probabilidades. Un oráculo de IA intenta resolver cada pregunta
buscando en la web, y el código decide si acepta su veredicto. Todo corre en
Google Cloud.

La segunda parte es una **nube autónoma que actúa sobre Cloud Run de verdad**:
- Despliega la topología que propone un modelo generativo.
- Escala con el tráfico de los móviles de la sala.
- Repara fallas reales.
- Tiene un **mercado real**: agentes con servicios propios venden peticiones
  reales, con costos tomados del catálogo de precios de Cloud Billing, forman
  coaliciones que se ejecutan y evolucionan según la ganancia que de verdad
  obtienen.

Un laboratorio simulado de doce agentes muestra las mismas técnicas a cámara
rápida. La sala apuesta sobre lo que pasará. Ver
[La nube autónoma](#la-nube-autónoma).

Hay una demo desplegada en el proyecto `oraculo-6d1578`, en
https://oraculo-api-346171942822.us-east1.run.app. Ver
[Publicar en Google Cloud](#publicar-en-google-cloud).

## Las tres pantallas

| Pantalla | Quién la ve | Qué muestra | Qué te dice en pantalla |
| --- | --- | --- | --- |
| `/` | La audiencia, en el móvil | Las preguntas, el precio y los botones para apostar; el censo privado si la pregunta es de la sala | Que no busquen; que el nombre no es una cuenta; si hay infraestructura real, que **su móvil es la demanda** que escala la nube y que los agentes se disputan |
| `/proyeccion.html` | Todos, en el proyector | Cada mercado, su precio, quién lo resuelve y la línea «la sala decía X; el juez dice Y» | Qué mide cada tipo de pregunta, con una etiqueta distinta para «Nube simulada» y «Nube real · Cloud Run»; cómo ver los controles si falta la clave |
| `/nube.html` | El ponente, en el proyector | La infraestructura real, el **mercado real** (agentes, precios del catálogo, subastas, contratos, generaciones), la política de actuación, los incidentes y el laboratorio simulado | Una guía plegable «Cómo usar esta página», ayuda al pasar el cursor por cada botón, una **pista que cambia con el estado** en la infraestructura y otra en el mercado real, y las tarjetas del laboratorio marcadas como simuladas |

Los controles del ponente solo aparecen si la URL termina en `#clave=…`. Sin
la clave, las tres pantallas siguen funcionando como vistas de solo lectura.

Antes de tocar el código, conviene tener claras tres cosas: qué predice
realmente este mercado, por qué vale la pena mostrarlo y qué no se puede afirmar
con él desde el escenario.

## Qué está prediciendo

Cada mercado declara su tipo (`kind`), porque el tipo cambia lo que mide el
precio:

| Tipo | Ejemplo | Qué mide el precio | Quién lo resuelve |
| --- | --- | --- | --- |
| `presente` | ¿Salió Python 3.15.0 antes del 15/10/2026? | La respuesta ya existe en algún servidor y se puede verificar, pero nadie en la sala la sabe con certeza. El precio agrega conocimiento disperso **sobre el presente**: Hayek, no Hanson. | El oráculo, con evidencia |
| `futuro` | ¿Cerrará el USD/DOP sobre 65 el 31/12/2026? | Hoy no se puede resolver, y eso es a propósito: lo correcto es que el oráculo diga **SIN RESOLVER**. Con esta pregunta el mercado también apuesta sobre sí mismo, sobre si la pregunta admite respuesta todavía. | El oráculo, que debe negarse |
| `sala` | ¿Más de la mitad de esta sala desplegó un viernes este mes? | Cada asistente conoce una parte de la respuesta y ningún buscador la tiene. Es el caso en el que el mecanismo de agregación realmente se luce. | Un censo privado de la sala |
| `simulacion` | ¿La primera caída de nodo se reparará en menos de 6 ticks? | Nadie lo sabe, porque el comportamiento de los agentes es emergente. Es un futuro de verdad, con plazo de minutos. | El código de la simulación |
| `simulacion` con predicado real | ¿La primera falla en un nodo real de Cloud Run se reparará sola en menos de 2 minutos? | Lo mismo, pero sobre infraestructura real: depende de cuánto tarde Cloud Run en desplegar una revisión. | Lo medido en Cloud Run (`InfraController`) |

Las preguntas `presente` se pueden buscar en Google. Por eso, en el fondo, son
una carrera entre la corazonada de la sala y un buscador. La interfaz pide que
nadie busque, y si alguien lo hace también sirve para la charla: esa persona se
convierte en el buscador y el precio se mueve con su información.

## Por qué es interesante

**Dos formas de conocer, lado a lado.** El mercado agrega creencia: ochenta
personas apostando producen un número. El oráculo recupera evidencia: busca y
cita fuentes primarias. Cuando el oráculo resuelve, la API guarda el precio de
ese momento (`price_yes`), y la vista de proyección muestra el contraste en una
línea:

> La sala decía **70 % SÍ**; el oráculo dice **NO** con 2 fuentes.

**El LLM como componente no confiable.** Casi todos los demos de LLM muestran
un modelo que produce algo y piden que confíes en el resultado. Este hace lo
contrario: el modelo produce algo y el código lo rechaza. El modelo está detrás
de un puerto (`OracleGateway`), y una compuerta de política (`AcceptancePolicy`) decide si
el veredicto vale. El momento más instructivo de la charla es cuando el sistema
se niega a responder. Ese patrón es lo que la audiencia puede aplicar el lunes
en su trabajo.

Para que esos rechazos se puedan provocar en el escenario, la vista de
proyección tiene un selector de fallos:

| Fallo | Qué simula | Qué lo rechaza |
| --- | --- | --- |
| `baja_confianza` | El modelo responde con confianza 0.55 | `AcceptancePolicy`: confianza < `ORACLE_MIN_CONFIDENCE` |
| `un_dominio` | El grounding trae fuentes de un solo dominio | `AcceptancePolicy`: dominios < `ORACLE_MIN_SOURCES` |
| `json_malformado` | El modelo responde en prosa | `interpret`: fail-closed al no poder parsear |
| `red_caida` | Falla la llamada a Vertex AI | `run`: fail-closed ante cualquier excepción |

Los fallos se inyectan en la respuesta cruda, antes de que la lea `interpret`,
que es el mismo código que lee a Vertex AI. Funcionan igual con el modelo real
que con el simulado. Lo que la sala ve rechazar es la ruta de producción, no
una simulación aparte. Cada consulta queda registrada en `attempts`, con su
fallo, el precio de la sala en ese momento y el motivo del rechazo.

## La nube autónoma

`/nube.html` muestra una nube que intenta gobernarse sola: una parte simulada y,
si lo activas, una parte real sobre Cloud Run. La visión
completa (infraestructura que se auto-gobierna, se auto-optimiza y se
auto-repara en un mercado descentralizado) es mucho más grande de lo que cabe
en una charla, y casi todo en ella es todavía investigación. Por eso cada pieza
está construida en su versión más pequeña que todavía es honesta, y la
interfaz dice cuál es:

| La visión pide | Lo que hay aquí | Dónde | Lo que **no** es |
| --- | --- | --- | --- |
| Predecir la demanda y ajustar la oferta en tiempo real | **Real:** Holt predice las peticiones por segundo de la sala y fija las instancias mínimas de los nodos de Cloud Run. **Simulado:** Holt-Winters con autoescalado por agente | `application/infra.py`, `domain/cloud/forecast.py` | No es un modelo profundo. La demanda real son los móviles de la sala, no tráfico de producción |
| Descubrir estrategias de fijación de precios | **Real:** cada agente del mercado real ajusta su margen con Q-learning; la recompensa es su ganancia real (ingreso por peticiones atendidas a tiempo menos el costo real de Cloud Run). **Laboratorio:** lo mismo sobre doce agentes simulados | `real_market.py`, `agents.py` | No es RL profundo. Son unos pocos estados y 3 acciones |
| Formar coaliciones | **Real:** contratos de peticiones que ningún agente atiende solo y que exigen dos regiones; la coalición los ejecuta de verdad, se paga solo si cumple, y se reparte por valor de Shapley exacto. **Laboratorio:** lo mismo con cpu simulada | `real_market.py`, `coalitions.py` | La formación es codiciosa, no un equilibrio negociado |
| Teoría de juegos evolutiva | Proporción de cada estrategia por generación, contra lo que predice la dinámica del replicador | `evolution.py` | El algoritmo genético no es el replicador: la vista muestra cuándo se separan |
| Evolucionar por mutación y selección | **Real:** el genoma incluye `warm` (pagar una instancia mínima o arriesgar arranques en frío). Mutarlo cambia la configuración real del servicio; la aptitud es la ganancia real. **Laboratorio:** algoritmo genético sobre doce agentes | `real_market.py`, `evolution.py` | No se reescriben a sí mismos. Evolucionan tres parámetros |
| Detectar y responder a fallas | **Real:** sondeos con token de identidad a cada nodo de Cloud Run; el detector EWMA ve la falla y la repara desplegando una revisión sana. **Simulado:** lo mismo sobre nodos ficticios | `application/infra.py`, `anomaly.py` | La falla real se inyecta (una revisión con `NODO_FALLA`), no es una caída espontánea |
| Generar arquitecturas | Gemini propone topologías; un algoritmo genético compite con él; `TopologyPolicy` acepta o rechaza a ambos. **Real:** la topología adoptada se despliega como servicios `oraculo-nodo-<región>`, después de pasar también por `ActuationPolicy` | `topology.py`, `domain/cloud/infra.py`, `adapters/infra/` | El modelo nunca llama a la nube. Dos compuertas en código se interponen |
| Mercado de recursos | **Real:** subasta de precio uniforme de la demanda real de la sala entre los agentes, con un tope de 12 peticiones por ciclo | `auction.py`, `real_market.py` | **No es descentralizado**: hay un subastador central. El dinero es contable: nadie le paga a un agente, pero cada costo es lo que Google Cloud cobra de verdad |
| Pipelines de CI/CD en Google Cloud | `cloudbuild.yaml`: pruebas → imagen → Artifact Registry → Cloud Run | raíz del repo | El pipeline despliega la API; los nodos los despliega el controlador |

### Qué es real y qué no

Con `INFRA_MODE=real` y la actuación activa, todo esto actúa sobre Cloud Run de
verdad:

| Bucle | Qué es real |
| --- | --- |
| Predicción y autoescalado | Holt predice las peticiones reales de la sala y fija las instancias mínimas reales |
| Detección y reparación | Sondeos reales con token de identidad; la reparación despliega una revisión sana |
| Topología | La que propone Gemini o la búsqueda evolutiva se despliega como `oraculo-nodo-<región>`. El costo de cada región es la proporción real de precios de Cloud Run; latencia y disponibilidad del catálogo son estimaciones |
| Mercado real | 4 agentes, cada uno con su servicio `oraculo-agente-<id>`. Venden peticiones reales de trabajo; los costos salen del catálogo de Cloud Billing en vivo; solo cobran lo atendido a tiempo (1 s) |
| Coaliciones | Contratos que exigen atender desde dos regiones, ejecutados de verdad y pagados solo si cumplen |
| Evolución | Cada 12 ciclos, selección y mutación con la ganancia real como aptitud. El gen `warm` cambia la instancia mínima real |

Lo que sigue simulado: el **laboratorio de doce agentes** (tarjetas marcadas
«laboratorio simulado» en `/nube.html`), que muestra las mismas técnicas a
cámara rápida y alimenta las preguntas `simulacion` de la sala. El dinero del
mercado real es contable: ningún agente recibe un pago, pero cada costo
corresponde a algo que Google Cloud cobra de verdad, y cada ingreso, a una
petición que de verdad se atendió a tiempo.

Entre una decisión y la nube hay dos compuertas en código:

1. `TopologyPolicy`: ¿es un buen diseño? Presupuesto, regiones, disponibilidad,
   latencia.
2. `ActuationPolicy`: ¿se puede ejecutar en esta cuenta? Regiones permitidas,
   3 servicios como máximo, 2 instancias mínimas en total, 2 máximas por región,
   un cambio de escala por minuto por región, 3 llamadas por ciclo, y solo
   servicios `oraculo-nodo-*` con la etiqueta `oraculo-demo=true`. Recorta el
   deseo antes de planificar y revisa cada acción antes de ejecutarla.

La actuación arranca **en pausa**: nada se crea hasta que el ponente la activa
desde `/nube.html`. `INFRA_MODE` puede ser `apagado` (el predeterminado),
`ensayo` (nube falsa en memoria), `plan` (Cloud Run valida cada acción con
`validateOnly` sin aplicarla) o `real`.

La parte simulada es determinista dada la semilla (`SIM_SEED`) y las acciones
del ponente.

### El mercado real, con números

Los precios vienen de la API pública de Cloud Billing (precios de lista, sin
descontar el nivel gratuito, para no subestimar). El 2026-10-05, en us-east1:

| Concepto | Costo |
| --- | --- |
| Una petición de trabajo (¼ vCPU, 256 MiB, redondeada a 100 ms) | 1,06 µUSD |
| Una hora con instancia mínima encendida | 0,45 centavos (0,63 en regiones de nivel 2) |
| Una hora de mercado con 12 peticiones cada 10 s y un agente caliente | ≈ 1 centavo |

Con el tráfico de una sala, mantener una instancia caliente cuesta más de lo
que se gana evitando arranques en frío. La evolución suele descubrirlo y
apagarla. No está programado: es la economía real de Cloud Run.

**Medido en producción el 2026-10-05**, 5 minutos y 24 ciclos con 4 agentes:

| Agente | Región | Latencia real (p50) | Resultado |
| --- | --- | --- | --- |
| r1 | us-east1 | 14 ms | Gana: la misma región que la API |
| r2 | us-central1 | 55 ms | Gana menos |
| r3 | europe-west1 | 111 ms | Gana; mejor de la generación 2 |
| r4 | southamerica-east1 | 138 ms | Pagó instancia caliente en una región de nivel 2 y casi no vendió: −157 µUSD. En la generación 2, la evolución le apagó la instancia |

- **Contratos:** los tres contratos de dos regiones se cumplieron, 6 de 6 a tiempo.
- **Costo total del mercado:** 531 µUSD, es decir, 0,05 centavos.
- **Peticiones:** 468, todas con 200.

Las latencias son de la API en us-east1 hacia cada región: la geografía es
real, no está en ningún catálogo.

### El mismo patrón que el oráculo

La pieza que conecta las dos mitades es la generación de topologías. Gemini
recibe las restricciones en el prompt, y aun así puede ignorarlas, inventar una
región o responder en prosa. `TopologyPolicy` vuelve a revisarlo todo:
presupuesto, regiones mínimas, disponibilidad, latencia y forma. El generador
simulado alterna a propósito entre propuestas buenas y malas para ensayar cada
rechazo. Y el algoritmo genético suele ganarle al modelo, lo que también vale
la pena decir en voz alta.

### Lo que la simulación ya enseña, sin que nadie lo programe

- **El margen se va a cero.** El Q-learning de los doce agentes empuja los
  precios hacia el costo: es competencia de Bertrand. Con un bien homogéneo y
  muchos vendedores, bajar el precio siempre roba ventas. Los precios solo
  suben cuando hay escasez.
- **La cooperación no siempre sobrevive.** Con unas semillas los cooperativos
  dominan; con otras se extinguen en dos generaciones. Por eso la pregunta
  «¿más del 40 % será cooperativo?» sirve para apostar.
- **Predecir bien es difícil de demostrar.** Sin perturbaciones, Holt-Winters
  apenas le gana al pronóstico ingenuo. Con picos de demanda, la diferencia
  crece.

### Qué afirmar sobre esta parte

- ✗ «Esta nube se gobierna sola». Los bucles actúan de verdad, pero sobre unos
  pocos servicios con límites duros y con un presupuesto de centavos por hora.
- ✓ «Estos son los bucles que una nube autónoma necesitaría: predecir, fijar
  precios, cooperar, reparar, evolucionar, diseñar. Así se ve cada uno en su
  forma más pequeña, y aquí es donde el código le dice que no al modelo».

Con `SIM_SEED` fija, el resultado es reproducible. Ensáyalo y decide si
quieres llegar a la charla sabiendo las respuestas o cambiar la semilla ese
mismo día.

## Qué afirmar desde el escenario

Este mercado no predice nada útil desde el punto de vista epistemológico. Con
ochenta personas, dinero ficticio, cuarenta minutos y tres preguntas no se
puede sostener ninguna afirmación sobre la sabiduría de las multitudes.

Eso solo importa si haces la afirmación equivocada:

- ✗ «Miren, la multitud acertó». Te van a desarmar, y con razón: es una muestra
  de tamaño uno.
- ✓ «Así se ve un mecanismo de agregación. Ninguno de ustedes sabía la
  respuesta, y aun así el precio se movió hacia ella». Es cierto y es más
  interesante.

La vista de proyección está construida para la segunda frase. Todos los
mercados abren en 50 %, sin órdenes sembradas por la casa, así que cualquier
movimiento lo hizo la sala. Al resolver, la vista dice si el precio se había
movido hacia la respuesta o en contra, y nunca afirma que «la multitud
acertó».

### Decide qué charla das

La charla que das cambia qué preguntas siembras. Se elige con `SEED_SET`:

| `SEED_SET` | Preguntas | Charla |
| --- | --- | --- |
| `oraculo` (default) | Kubernetes, Python (`presente`) y USD/DOP (`futuro`) | Creencia contra evidencia, y el LLM como componente no confiable. El mecanismo de mercado es decorado. |
| `agregacion` | Tres preguntas `sala` sobre la práctica de la audiencia | El mecanismo de agregación. La información está dispersa de verdad y no se puede buscar. El oráculo casi no aparece. |
| `mixta` | Python, USD/DOP y una pregunta `sala` | Un ejemplo de cada tipo. Es la más completa, aunque pide más tiempo. |
| `nube` | Tres preguntas `simulacion`: cooperación, autorreparación y la topología del modelo | La nube autónoma. La sala apuesta sobre comportamiento emergente y el código resuelve. |
| `nube_real` | Cooperación y topología (simuladas) más la autorreparación de un nodo real de Cloud Run | La nube autónoma tocando infraestructura real. Necesita `INFRA_MODE=real`; con la infraestructura apagada, la pregunta real queda SIN RESOLVER. |

Para sembrar tus propias preguntas `sala`, busca algo que cada asistente sepa
de sí mismo y que nadie sepa del grupo: prácticas, hábitos, incidentes
recientes. Evita lo que se resuelve con una búsqueda.

### Límites del censo, para decirlos antes de que los pregunten

- El censo es autodeclarado y quien responde también apuesta. Alguien puede
  mentir en el censo para ganar su apuesta. La mitigación es débil: una
  respuesta por persona, inmutable, y solo se publica el conteo. Con dinero
  ficticio el incentivo para mentir es bajo, pero existe.
- Con menos de 5 respuestas el censo se niega a resolver (`CENSUS_MIN_RESPONSES`). Es la
  misma idea que el mínimo de fuentes del oráculo.
- Los nombres no se autentican. Para una sala está bien; para cualquier otra
  cosa, no.

### Guion sugerido (≈ 40 min)

1. **Apertura (5 min).** Proyecta `/proyeccion.html` y la audiencia entra en
   `/`. Explica los tres tipos con la tarjeta de cada mercado.
2. **Mercado abierto (15 min).** Deja operar a la sala. Señala cómo se mueve el
   precio, siempre como mecanismo y nunca como acierto.
3. **La negativa (5 min).** Consulta al oráculo sobre la pregunta `futuro`.
   Luego inyecta `baja_confianza` y `un_dominio` en una pregunta `presente` y
   lee la traza en voz alta: el modelo propuso, el código rechazó.
4. **El contraste (5 min).** Consulta sin fallo. Lee la línea «la sala decía X
   %, el oráculo dice Y con N fuentes».
5. **Cierre (10 min).** Explica qué *no* demuestra esto. Muestra
   [`app/domain/verdict.py`](app/domain/verdict.py) y sus tests.

### Guion con `SEED_SET=nube` (≈ 40 min)

1. **Apertura (5 min).** Proyecta `/nube.html` en pausa. Recorre las seis
   tarjetas: cada una dice qué técnica es y qué no es.
2. **Apuestas (5 min).** La audiencia abre `/` y apuesta en las tres preguntas.
   Inicia la simulación.
3. **Fallas (10 min).** Inyecta una caída de nodo y un pico de demanda. Señala
   cuánto tarda el detector, si hubo falsos positivos y si el reemplazo salió
   defectuoso.
4. **El modelo propone (10 min).** Pide topologías al modelo y a la búsqueda
   evolutiva. Lee en voz alta la traza de un rechazo.
5. **Cierre (10 min).** Avanza hasta la generación 5 y resuelve los mercados
   desde `/proyeccion.html`. Termina con la tabla de «lo que no es».

### Guion con `SEED_SET=nube_real` (≈ 40 min)

La pista de `/nube.html` te dice en cada momento qué falta. Este es el orden
que funciona:

1. **Antes de entrar (5 min antes).** Abre `/nube.html#clave=…` y confirma que
   la tarjeta «Infraestructura real» dice `modo real` sin errores.
2. **Apertura (5 min).** Explica las dos compuertas: `TopologyPolicy` y
   `ActuationPolicy`. La sala abre `/` y apuesta.
3. **El modelo propone (5 min).** «Pedir al modelo»: Gemini propone y la
   política decide. Compara lo que el modelo *dice* de la latencia con lo que
   el código *mide*.
4. **La nube actúa (10 min).** «Activar actuación»: el primer ciclo crea los
   nodos y los servicios de los agentes en Cloud Run (unos 30 s). El tráfico
   de los móviles es la demanda: Holt la predice, la política enciende
   instancias y los agentes del mercado real se la disputan. Señala la tabla
   del mercado: quién vende, a qué latencia real, cuánto cuesta de verdad y
   quién paga una instancia caliente sin que le convenga.
5. **La falla real (10 min).** Cuando la pista diga «Listo para una falla
   real», pulsa «caída» en un nodo. Cuenta en voz alta: unos 30 s hasta que el
   detector la ve, unos 20 s más hasta que Cloud Run despliega la revisión sana.
6. **Cierre (5 min).** Resuelve los mercados desde `/proyeccion.html` y pulsa
   **Apagar todo**. Termina con la tabla de «lo que no es».

## Qué hay dentro

El código sigue clean architecture: las dependencias apuntan hacia adentro y el
centro no sabe que existen FastAPI, Vertex AI ni la memoria del proceso.

```
app/
├── domain/              Reglas puras. No importa nada del proyecto ni de I/O.
│   ├── lmsr.py          Market maker automático (LMSR de Hanson)
│   ├── market.py        Entidades Market y Account: órdenes, censo, liquidación
│   ├── verdict.py       Verdict, AcceptancePolicy y CensusPolicy
│   ├── errors.py
│   └── cloud/           La nube simulada, determinista dada la semilla
│       ├── catalog.py   Recursos, regiones y zonas de usuarios
│       ├── forecast.py  Holt-Winters aditivo
│       ├── auction.py   Subasta de precio uniforme
│       ├── agents.py    Genoma, Q-learner y autoescalado de cada agente
│       ├── coalitions.py  Contratos y valor de Shapley
│       ├── anomaly.py   Detector EWMA con z-score
│       ├── evolution.py Algoritmo genético y dinámica del replicador
│       ├── topology.py  Evaluación, TopologyPolicy y búsqueda evolutiva
│       ├── infra.py     Plan de acciones y ActuationPolicy
│       ├── real_market.py  Precios, genoma, subasta, liquidación y evolución del mercado real
│       ├── predicates.py  Qué puede preguntar la sala y quién lo resuelve
│       └── simulation.py  El tick, las fallas y el juez de los mercados
├── application/         Casos de uso y los puertos que necesitan.
│   ├── service.py       MarketService: crear, operar, censo, resolver
│   ├── cloud.py         CloudService: correr, pausar, fallas, topologías, juez
│   ├── infra.py         InfraController: observar, predecir, sondear, reparar, actuar
│   ├── judges.py        Juez compuesto: simulación o infraestructura real
│   ├── real_market.py   RealMarket: subasta la demanda real, envía trabajo, liquida, coaliciones, evolución
│   ├── limits.py        Límites de ritmo contra abuso
│   ├── ports.py         OracleGateway, Repository, SimulationJudge, TopologyGenerator
│   ├── views.py         Lo que sale de un caso de uso (dicts planos)
│   └── errors.py        NotFound, Cooldown
├── adapters/            Implementaciones de los puertos.
│   ├── memory.py        Repository en memoria, con lock
│   ├── google_auth.py   Credenciales por defecto y tokens de identidad
│   ├── vertex_client.py generateContent, compartido
│   ├── infra/           Nodos y agentes: Cloud Run (Admin API v2) y nube de ensayo
│   ├── prices.py        Precios de Cloud Run: catálogo de Cloud Billing o foto fija
│   ├── topology/        Generadores de topologías: Vertex AI y simulado
│   └── oracle/
│       ├── gemini.py    Ruta común: run → inject_fault → interpret → política
│       ├── vertex.py    Gemini en Vertex AI con grounding
│       └── mock.py      Simulado, con la misma forma de respuesta
├── entrypoints/http/    FastAPI: rutas, esquemas, clave de ponente y estáticos
│   └── static/          Tres pantallas con su JS aparte (CSP sin scripts en línea)
├── node.py            El nodo real: /salud (con NODO_FALLA) y /trabajo, lo que venden los agentes
├── config.py            Settings: el único que lee el entorno; falla cerrado en producción
├── seeds.py             Juegos de preguntas (SEED_SET)
└── main.py              Raíz de composición: conecta las capas
```

| Capa | Puede importar | No puede importar |
| --- | --- | --- |
| `domain` | solo `domain` | FastAPI, Pydantic, httpx, google, `os` |
| `application` | `domain` | lo mismo que `domain` |
| `adapters` | `domain`, `application` | `entrypoints` |
| `entrypoints` | `domain`, `application` | `adapters` |

[`tests/test_architecture.py`](tests/test_architecture.py) recorre los imports
con `ast` y falla si alguien rompe esta tabla. Los tests siguen las mismas
capas:

| Carpeta | Qué prueba | Cómo |
| --- | --- | --- |
| `tests/domain/` | LMSR, entidades, políticas, cada técnica de la nube, la simulación entera y la economía del mercado real (redondeo a 100 ms, plazo, reposo, tope de calientes) | Python puro, sin dobles, semillas fijas, precios de la foto del catálogo |
| `tests/application/` | Casos de uso, el controlador de infraestructura (crear, escalar, reparar, vigilia) y el mercado real (topes de costo, contratos, generaciones, apagado) | Oráculo, generadores y nube de ensayo falsos, reloj controlado |
| `tests/adapters/` | Lectura de grounding, cada fallo inyectado, qué pediría a la Admin API de Cloud Run, y la lectura del catálogo de precios | Payloads de `generateContent`, peticiones grabadas y SKUs reales guardados en `fixtures/`, sin red |
| `tests/entrypoints/` | API de punta a punta, incluidas las rutas `/api/infra` y su clave | `TestClient` con el oráculo simulado y la nube de ensayo |
| `tests/security/` | Cada control de [SECURITY.md](SECURITY.md): rutas sin autenticación, suplantación, cabeceras, CSP, scripts en línea, arranque inseguro, límites | Recorre las rutas de la app y los archivos estáticos |
| `tests/test_docs.py` | Que `docs/ARQUITECTURA.md` coincida con los `.mmd` y que los enlaces locales existan | Sin red |

## Arranque local

Requiere Python 3.12 o superior.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --require-hashes -r requirements.lock   # solo versiones fijadas, verificadas por hash
pip install -r requirements-dev.txt
pre-commit install                 # controles de seguridad antes de cada commit
cp .env.example .env

pytest -q
uvicorn app.main:app --reload --port 8080
```

- Audiencia: http://localhost:8080
- Proyección: http://localhost:8080/proyeccion.html
- Nube autónoma: http://localhost:8080/nube.html

`SIM_TICK_SECONDS=0.1` acelera la simulación para ensayar: una generación en
2,4 s.

Para ensayar la parte real sin tocar Google Cloud, usa la nube de ensayo en
memoria. Se comporta como Cloud Run: los cambios tardan un par de ciclos y las
fallas se ven en los sondeos.

```bash
SEED_SET=nube_real INFRA_MODE=ensayo INFRA_INTERVALO=2 INFRA_RPS_POR_INSTANCIA=1 \
  uvicorn app.main:app --port 8080
```

Abre `/nube.html`, activa la actuación y deja `/` abierta en otra pestaña para
generar demanda. `INFRA_MODE=plan` es el paso siguiente: habla con Cloud Run de
verdad, pero con `validateOnly`, así que no crea nada.

Si `GOOGLE_CLOUD_PROJECT` no está configurado, el oráculo usa el adaptador
simulado: no toca la red y devuelve veredictos deterministas. Es el modo
correcto para ensayar la charla. `ORACLE_MOCK_FORCE=YES|NO|UNRESOLVED` fija el
veredicto simulado.

En VS Code, F5 arranca la API con recarga y el panel de pruebas descubre la
suite automáticamente. Las extensiones recomendadas aparecen al abrir la
carpeta.

### Clave de ponente

Crear y resolver mercados es tarea del ponente, no de la audiencia. Si defines
`PRESENTER_KEY`, esas rutas exigen la cabecera `X-Presenter-Key`, y la vista de
proyección la lee del fragmento de la URL:

```
https://tu-servicio/proyeccion.html#clave=TU_CLAVE
```

El fragmento (`#…`) no viaja al servidor ni queda en los logs. Si no defines
`PRESENTER_KEY`, en local no se exige nada. **En Cloud Run, defínela siempre**:
sin ella, cualquiera de la sala puede consultar al oráculo y cerrar mercados
desde su móvil.

## Conectar Vertex AI de verdad

```bash
gcloud auth application-default login
gcloud services enable aiplatform.googleapis.com --project TU_PROYECTO
```

Luego pon `GOOGLE_CLOUD_PROJECT=TU_PROYECTO` y `ORACLE_BACKEND=vertex` en
`.env`. No hay llave de API: la autenticación usa las credenciales por defecto
del entorno. En Cloud Run, esas credenciales son la identidad de la cuenta de
servicio.

## Decisiones que conviene conocer antes de tocar el código

**El estado vive en memoria.** No hay base de datos, y el servicio se despliega
con `max-instances=1`. Es deliberado: el mercado dura 40 minutos. Si tuviera
que sobrevivir a un reinicio, el siguiente paso sería un adaptador de Firestore que implemente `Repository`; no
habría que tocar nada más.

**El modelo propone, el código dispone.** `AcceptancePolicy` decide si un veredicto
se acepta. Exige confianza mínima y al menos dos dominios independientes, y
falla cerrado (fail-closed) ante un error de red, JSON malformado o un
resultado desconocido. Un `UNRESOLVED` deja el mercado abierto. Esa función es
el corazón del sistema y sus tests son los que más vale la pena revisar.

**Una sola ruta de interpretación.** Vertex AI y el simulado devuelven el mismo
formato de `generateContent` y pasan por `run → inject_fault → interpret →
AcceptancePolicy`. No agregues lógica de aceptación en un adaptador: la
política vive en el dominio, y si algo no está en la ruta común, el ensayo
deja de probar lo que se usa en producción.

**La evidencia no la escribe el modelo.** Sale de `groundingMetadata`, que
Vertex AI adjunta según lo que realmente buscó. Ojo con un detalle: los `uri`
de los grounding chunks son enlaces de redirección y todos comparten host, así
que el dominio real se lee del campo `domain` y no de la URL. Hay un test que
fija ese comportamiento; no lo borres pensando que es redundante.

**El censo no pasa por el oráculo.** Las preguntas `sala` se resuelven con
`CensusPolicy`, que aplica la misma idea de fail-closed (mínimo de
respuestas). Las respuestas individuales nunca salen de la API: solo se publica
`census_count`.

**Los umbrales se inyectan, no se leen del entorno.** `config.py` lee las
variables y `main.py` construye las políticas con esos valores. El dominio
recibe números, no sabe de dónde vienen, y un test puede usar umbrales distintos
sin tocar el entorno. La única excepción es `ORACLE_MOCK_FORCE`, que el
simulado lee en cada llamada para poder cambiarlo a mitad de un ensayo.

**Los mercados abren en 50 %.** Antes se sembraban órdenes de la casa para que
el tablero pareciera vivo. Eso contaminaba la única afirmación honesta de la
charla («el precio se movió»), así que se quitó.

**Nada corre en segundo plano.** La simulación calcula en cada petición
cuántos ticks tocan según el reloj y los ejecuta, hasta 50 por petición. El
controlador de infraestructura corre un ciclo dentro de `GET /api/infra` cuando
pasaron 10 s desde el anterior. Por eso la API puede usar facturación por
petición y escalar a cero: si nadie mira `/nube.html`, el controlador no
trabaja ni cobra.

**Los nodos olvidados son el único gasto que no se apaga solo.** Una instancia
mínima cobra aunque la API duerma. La vigilia (`POST /api/infra/vigilia`, que
Cloud Scheduler llama cada 15 min) borra los nodos si nadie miró la proyección
en `INFRA_TTL_SEGUNDOS`. Un proceso recién arrancado asume que nadie mira, para
que una API recién despertada limpie lo que dejó la sesión anterior.

**Dos compuertas antes de la nube.** `TopologyPolicy` decide si un diseño es
bueno; `ActuationPolicy` decide si se puede ejecutar en esta cuenta. La
segunda recorta el deseo antes de planificar y vuelve a revisar cada acción.
El adaptador de Cloud Run agrega una tercera defensa: solo construye nombres
`oraculo-nodo-*` y nunca toca un servicio sin la etiqueta `oraculo-demo=true`.

**Cloud Run reserva las rutas que terminan en `z`.** `/healthz` responde 404
desde Google, no desde la app. La API expone `/api/salud` y los nodos `/salud`.

**Los modelos gemini-2.5 se retiran el 20 de octubre de 2026.** El default es
`gemini-3.8-flash`, configurable con `ORACLE_MODEL`.

## Contenedor

```bash
docker build -t oraculo-api:dev .
docker run -p 8080:8080 -e ORACLE_BACKEND=mock -e SEED_SET=mixta oraculo-api:dev
```

## Publicar en Google Cloud

Cloud Run, con la imagen construida en Cloud Build y guardada en Artifact
Registry. No hace falta Docker local. Estos comandos son los que se usaron para
crear el proyecto `oraculo-6d1578`.

### Costos: qué cobra y qué no

| Recurso | Cuándo cobra | Cómo se contiene |
| --- | --- | --- |
| API `oraculo-api` | Solo mientras atiende peticiones | Facturación por petición (`--cpu-throttling`) y escala a cero (`--min-instances 0`) |
| Bucle de infraestructura | Nunca por sí solo | No hay bucle de fondo: corre dentro de las consultas de `/nube.html`, cada 10 s, solo mientras alguien mira |
| Nodos `oraculo-nodo-*` | Las instancias mínimas cobran aunque nadie las use | ¼ de vCPU y 256 MiB; 2 instancias mínimas en total como máximo; los nodos sin demanda quedan en cero |
| Agentes `oraculo-agente-*` | Solo las peticiones que atienden, y la instancia mínima si su gen `warm` está activo | Sin instancia mínima por defecto; como mucho 1 agente caliente (0,45 centavos por hora en us-east1); 12 peticiones de trabajo por ciclo (≈ 1 µUSD cada una) |
| Nodos y agentes olvidados | Si la API duerme, siguen ahí | Vigilia: Cloud Scheduler llama a `/api/infra/vigilia` cada 15 min y, si nadie miró la proyección en 30 min, borra todos los nodos y agentes |
| Gemini | Por llamada | Solo cuando el ponente pide una topología o resuelve una pregunta del oráculo |
| Imágenes | Almacenamiento | Política de limpieza: se conservan las 3 más recientes |
| Todo el proyecto | — | Presupuesto de 10 USD/mes con alertas al 50, 90 y 100 %. **Un presupuesto alerta, no corta**: el freno son la vigilia y la política |

Con la escala a cero, el estado del mercado se pierde cuando la API duerme. En
una charla no pasa, porque los móviles la mantienen despierta.

**Durante la charla, sube a `--min-instances 1`.** Con mínimo 0 y máximo 1, las
peticiones que llegan mientras la única instancia arranca en frío reciben un
429 de Cloud Run, antes de llegar a la app. Pasó en una prueba: ocho peticiones
a la vez justo después de desplegar. Cuesta unos 1,4 centavos por hora (1 vCPU
y 512 MiB en reposo):

```bash
gcloud run services update oraculo-api --region us-east1 --min-instances 1   # antes de empezar
gcloud run services update oraculo-api --region us-east1 --min-instances 0   # al terminar
```

### Una sola vez: proyecto, APIs e identidades

```bash
export PROJECT_ID=oraculo-$(openssl rand -hex 3)   # "oraculo" a secas ya está tomado
export REGION=us-east1                              # la más cercana a Santo Domingo
export BILLING=$(gcloud billing accounts list --filter=open=true --format='value(name)' --limit=1)

gcloud projects create $PROJECT_ID --name=oraculo
gcloud billing projects link $PROJECT_ID --billing-account=$BILLING
gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  aiplatform.googleapis.com iam.googleapis.com cloudscheduler.googleapis.com billingbudgets.googleapis.com \
  secretmanager.googleapis.com

# Si da IAM_PERMISSION_DENIED justo después de activar las APIs, espera un minuto y repite.
gcloud artifacts repositories create oraculo --repository-format=docker --location=$REGION

RUN=oraculo-run@$PROJECT_ID.iam.gserviceaccount.com         # la API y el controlador
NODO=oraculo-nodo@$PROJECT_ID.iam.gserviceaccount.com       # los nodos: sin ningún rol
VIG=oraculo-vigilia@$PROJECT_ID.iam.gserviceaccount.com     # Cloud Scheduler: sin ningún rol
gcloud iam service-accounts create oraculo-run --display-name="oraculo-api en Cloud Run"
gcloud iam service-accounts create oraculo-nodo --display-name="Nodos reales (sin roles)"
gcloud iam service-accounts create oraculo-vigilia --display-name="Cloud Scheduler: vigilia (sin roles)"

# La clave de ponente vive en Secret Manager, legible solo por oraculo-run.
openssl rand -hex 16 | tr -d '\n' | gcloud secrets create oraculo-presenter-key \
  --replication-policy=user-managed --locations=$REGION --data-file=-
gcloud secrets add-iam-policy-binding oraculo-presenter-key \
  --member="serviceAccount:$RUN" --role=roles/secretmanager.secretAccessor

for role in roles/aiplatform.user roles/run.developer roles/run.invoker; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$RUN" --role=$role --condition=None
done
# Desplegar nodos que corren como oraculo-nodo, con la imagen del repositorio:
gcloud iam service-accounts add-iam-policy-binding $NODO --member="serviceAccount:$RUN" \
  --role=roles/iam.serviceAccountUser
gcloud artifacts repositories add-iam-policy-binding oraculo --location=$REGION \
  --member="serviceAccount:$RUN" --role=roles/artifactregistry.reader

# Cloud Build construye con la cuenta de Compute en proyectos nuevos.
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
BUILDER=$PROJECT_NUMBER-compute@developer.gserviceaccount.com
for role in roles/cloudbuild.builds.builder roles/run.developer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$BUILDER" --role=$role --condition=None
done
gcloud iam service-accounts add-iam-policy-binding $RUN --member="serviceAccount:$BUILDER" \
  --role=roles/iam.serviceAccountUser

# Ahorro: imágenes viejas fuera, y alertas de gasto.
cat > /tmp/limpieza.json <<'JSON'
[{"name": "conservar-3-recientes", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 3}},
 {"name": "borrar-el-resto", "action": {"type": "Delete"}, "condition": {"tagState": "any", "olderThan": "1d"}}]
JSON
gcloud artifacts repositories set-cleanup-policies oraculo --location=$REGION --policy=/tmp/limpieza.json --no-dry-run
gcloud billing budgets create --billing-account=$BILLING --display-name="oraculo: tope de la demo" \
  --budget-amount=10USD --filter-projects=projects/$PROJECT_ID \
  --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
```

Por qué cada permiso, y por qué ninguno más:

- `run.developer`: crear, escalar y borrar los nodos. No incluye cambiar
  permisos IAM de servicios, así que los nodos no pueden volverse públicos.
- `run.invoker`: sondear los nodos, que son privados, con un token de identidad.
- `serviceAccountUser` solo sobre `oraculo-nodo`: los nodos corren con una
  identidad sin roles; si alguien compromete uno, no obtiene nada.
- `artifactregistry.reader` solo sobre el repositorio: Cloud Run comprueba que
  quien despliega pueda leer la imagen. Sin este permiso, crear un nodo da 403.
- `secretAccessor` solo sobre `oraculo-presenter-key`: la API lee su clave y
  ningún otro secreto.
- `oraculo-vigilia` no tiene roles: solo firma el token OIDC con el que Cloud
  Scheduler se presenta ante la API.

### Construir y desplegar

El primer despliegue se hace a mano, porque define la identidad, el secreto y
las variables. Los siguientes los hace el pipeline, que pasa por todas las
compuertas de seguridad antes de publicar.

```bash
IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/oraculo/oraculo-api:inicial
gcloud builds submit --tag $IMAGE

gcloud run deploy oraculo-api --image $IMAGE --region $REGION --service-account $RUN \
  --allow-unauthenticated --cpu-throttling --min-instances 0 --max-instances 1 \
  --concurrency 250 --cpu 1 --memory 512Mi \
  --set-secrets PRESENTER_KEY=oraculo-presenter-key:latest \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT_ID,ORACLE_BACKEND=vertex,VERTEX_LOCATION=global,\
SEED_SET=nube_real,SIM_SEED=7,INFRA_MODE=real,NODO_IMAGEN=$IMAGE,NODO_CUENTA=$NODO"

URL=$(gcloud run services describe oraculo-api --region $REGION --format='value(status.url)')
gcloud run services update oraculo-api --region $REGION \
  --update-env-vars "VIGILIA_CUENTA=$VIG,VIGILIA_AUDIENCIA=$URL/api/infra/vigilia"
gcloud scheduler jobs create http oraculo-vigilia --location=$REGION --schedule="*/15 * * * *" \
  --uri="$URL/api/infra/vigilia" --http-method=POST \
  --oidc-service-account-email=$VIG --oidc-token-audience="$URL/api/infra/vigilia"

# De aquí en adelante, cada publicación:
gcloud builds submit --config cloudbuild.yaml --region $REGION
```

- `--max-instances 1`: el estado vive en memoria; con dos instancias habría
  dos mercados.
- `--cpu-throttling --min-instances 0`: la API solo cobra mientras responde.
- `--set-secrets`: la clave nunca aparece como variable de entorno legible en
  la consola.
- Cloud Scheduler se autentica con un token OIDC firmado por Google; la API
  verifica firma, audiencia y cuenta. No comparte ningún secreto.
- En Cloud Run la API **se niega a arrancar** sin una clave de al menos 32
  caracteres, y cierra `/api/docs`.
- `SEED_SET` puede ser `oraculo`, `agregacion`, `mixta`, `nube` o `nube_real`.
- `INFRA_MODE=plan` es un buen primer paso: Cloud Run valida cada acción y no
  crea nada.

### Comprobar

```bash
curl $URL/api/salud     # {"ok":true}. Cloud Run reserva las rutas que terminan en "z", como /healthz
curl $URL/api/info      # "oracle":"vertex"
curl -sI $URL/ | grep -i content-security-policy
PRESENTER_KEY=$(gcloud secrets versions access latest --secret=oraculo-presenter-key)
echo "Audiencia:  $URL"
echo "Proyección: $URL/proyeccion.html#clave=$PRESENTER_KEY"
echo "Nube:       $URL/nube.html#clave=$PRESENTER_KEY"
```

### Durante y después de la charla

En `/nube.html`, **Activar actuación** pone a los bucles a actuar. **Apagar
todo** borra los nodos y pausa. Si te olvidas, la vigilia los borra a los 30
minutos sin nadie mirando. Para comprobar que no quedó nada:

```bash
# Sin --region lista todas las regiones (--region=- da error en gcloud 490).
gcloud run services list --filter="metadata.labels.oraculo-demo=true"
# borrar a mano lo que haya quedado:
for s in $(gcloud run services list --filter="metadata.labels.oraculo-demo=true" \
           --format="csv[no-heading](metadata.name,region)"); do
  gcloud run services delete ${s%,*} --region=${s#*,} --quiet
done
# o, para borrarlo todo (se puede recuperar durante 30 días):
gcloud projects delete $PROJECT_ID
```

Cambia la clave de ponente después de cada charla: vive en el historial del
navegador que proyectó.

```bash
openssl rand -hex 16 | tr -d '\n' | gcloud secrets versions add oraculo-presenter-key --data-file=-
gcloud run services update oraculo-api --region $REGION   # nueva revisión: lee la versión nueva
```

### CI/CD con Cloud Build

[`cloudbuild.yaml`](cloudbuild.yaml) es una cadena de compuertas: secretos
(gitleaks) → ruff con bandit → `pip-audit` → toda la suite → imagen → escaneo
con Trivy → publicar → desplegar. Si una falla, nada llega a producción. El
despliegue cambia la imagen de la API y `NODO_IMAGEN`, y conserva el resto de
la configuración y el secreto. Ver [SECURITY.md](SECURITY.md).

```bash
gcloud builds submit --config cloudbuild.yaml
```

Para que corra en cada push, conecta el repositorio de GitHub en la consola
(Cloud Build → Repositorios; la autorización de GitHub solo se puede hacer
ahí) y crea el trigger:

```bash
gcloud builds triggers create github --name=oraculo-main \
  --repo-owner=TU_USUARIO --repo-name=oraculo \
  --branch-pattern='^main$' --build-config=cloudbuild.yaml
```

Ojo: hoy trabajas en `master`, pero la rama principal del repositorio es
`main`. Ajusta `--branch-pattern` a la rama que de verdad publicas.

## Seguridad

El modelo de amenazas, cada control con el test que lo fija y los riesgos
aceptados están en [SECURITY.md](SECURITY.md). En resumen:

- **Audiencia:** un token por nombre (se guarda solo su hash), límites de ritmo
  y un tope de cuentas.
- **Ponente:** clave de 32 caracteres o más en Secret Manager, comparada en
  tiempo constante. Sin ella, producción no arranca.
- **Cloud Scheduler:** OIDC firmado por Google, sin secretos compartidos.
- **Pantallas:** CSP `script-src 'self'`, ningún script en línea y cabeceras de
  seguridad en todas las respuestas.
- **El modelo:** es un componente no confiable; dos políticas en código deciden.
- **La nube:** `ActuationPolicy`, identidades con permisos mínimos, nodos
  privados y sin roles.
- **Cadena de suministro:** lock con hashes, imagen base por digest y Trivy.

Los controles corren antes de cada commit (`pre-commit`), en cada build
(`cloudbuild.yaml`) y a mano con `make seguridad`.

## Pendiente

- Conectar el trigger de Cloud Build al repositorio de GitHub
- Persistir el estado si tuviera que sobrevivir a que la API escale a cero

## Diagramas

![Diagrama de contexto](docs/c4-nivel1-contexto.png)

[docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) reúne los cuatro diagramas C4
(contexto, contenedores, componentes y despliegue), dos diagramas de secuencia
(del modelo a Cloud Run, y la falla real con su reparación) y las fronteras de
confianza. GitHub los renderiza porque van en bloques `mermaid`.

Las fuentes son los archivos `docs/*.mmd`. Si editas uno, corre
`make diagramas`: copia el diagrama en `ARQUITECTURA.md` y renderiza otra vez
el de contexto. `tests/test_docs.py` falla si el documento quedó viejo.
