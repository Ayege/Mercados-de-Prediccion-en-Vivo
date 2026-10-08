# El código

Cómo está organizado, qué prueba cada carpeta de tests, cómo ensayar sin tocar
la nube y las decisiones que conviene conocer antes de cambiar algo. Los
diagramas C4 están en [ARQUITECTURA.md](ARQUITECTURA.md).

## Capas

Clean architecture: las dependencias apuntan hacia adentro y el centro no sabe
que existen FastAPI, Vertex AI ni la memoria del proceso.

| Capa | Puede importar | No puede importar |
| --- | --- | --- |
| `domain` | solo `domain` | FastAPI, Pydantic, httpx, google, `os` |
| `application` | `domain` | lo mismo que `domain` |
| `adapters` | `domain`, `application` | `entrypoints` |
| `entrypoints` | `domain`, `application` | `adapters` |

[`tests/test_architecture.py`](../tests/test_architecture.py) recorre los
imports con `ast` y falla si alguien rompe esta tabla.

```
app/
├── domain/              Reglas puras. No importa nada del proyecto ni de I/O.
│   ├── lmsr.py          Market maker automático (LMSR de Hanson)
│   ├── market.py        Market y Account: órdenes, censo, liquidación, historial acotado
│   ├── verdict.py       Verdict, AcceptancePolicy y CensusPolicy
│   ├── framing.py       FramingExperiment: titulares, asignación al azar, conteo por grupo; FramingPolicy
│   ├── media.py         NewsCoverage: medios, dietas, estado «leyendo»; NewsPolicy y cuánto apuesta cada agente
│   ├── errors.py
│   └── cloud/           La nube: laboratorio determinista y reglas del mercado real
│       ├── catalog.py   Recursos, regiones y zonas de usuarios
│       ├── forecast.py  Holt y Holt-Winters aditivo
│       ├── auction.py   Subasta de precio uniforme
│       ├── agents.py    Genoma (con credulidad), Q-learner y autoescalado de cada agente
│       ├── coalitions.py  Contratos y valor de Shapley
│       ├── anomaly.py   Detector EWMA con z-score
│       ├── evolution.py Algoritmo genético y dinámica del replicador
│       ├── topology.py  Evaluación, TopologyPolicy y búsqueda evolutiva
│       ├── infra.py     Plan de acciones y ActuationPolicy
│       ├── real_market.py  Precios, genoma, subasta, liquidación y evolución del mercado real
│       ├── predicates.py  Qué puede preguntar la sala y quién lo resuelve
│       └── simulation.py  El tick, las fallas, las noticias y el juez de los mercados
├── application/         Casos de uso y los puertos que necesitan.
│   ├── service.py       MarketService: crear, operar, censo, revelar; compone las dos de abajo
│   ├── accounts.py      Accounts: entrar con código de sala, token, límites de ritmo
│   ├── resolution.py    Resolver: censo, simulación u oráculo (con prueba de encuadre)
│   ├── news.py          NewsService: buscar noticias, abrir la pregunta, que opinen los agentes
│   ├── cloud.py         CloudService: correr, pausar, fallas, topologías, juez
│   ├── infra.py         InfraController: observar, predecir, sondear, reparar, actuar
│   ├── judges.py        Juez compuesto: simulación o infraestructura real
│   ├── real_market.py   RealMarket: subasta la demanda real, envía trabajo, liquida, evoluciona
│   ├── limits.py        Límites de ritmo contra abuso
│   ├── ports.py         OracleGateway (con OracleQuery), Repository, NewsDesk, NewsReader, …
│   ├── views.py         Lo que sale de un caso de uso (dicts planos)
│   └── errors.py        NotFound, Cooldown, …
├── adapters/            Implementaciones de los puertos.
│   ├── memory.py        Repository en memoria, con lock
│   ├── google_auth.py   Credenciales por defecto y tokens de identidad
│   ├── vertex_client.py generateContent, compartido
│   ├── prompt.py        Escapa el texto de terceros antes de meterlo en un prompt
│   ├── infra/           Nodos y agentes: Cloud Run (Admin API v2) y nube de ensayo
│   ├── prices.py        Precios de Cloud Run: catálogo de Cloud Billing o foto fija
│   ├── topology/        Generadores de topologías: Vertex AI y simulado
│   ├── news/            Búsqueda en Google News, editor y lectores (Vertex AI y simulados), lista de medios
│   └── oracle/
│       ├── gemini.py    Ruta común: run → inject_fault → interpret → política
│       ├── vertex.py    Gemini en Vertex AI con grounding; titulares como dato no confiable
│       └── mock.py      Simulado, con la misma forma de respuesta
├── entrypoints/http/    FastAPI: rutas async, esquemas, clave de moderación, auditoría y estáticos
│   └── static/          Tres pantallas con su JS aparte (CSP sin scripts en línea)
├── node.py              El nodo real: /salud (con NODO_FALLA) y /trabajo, lo que venden los agentes
├── config.py            Settings: el único que lee el entorno; falla cerrado en producción
├── seeds.py             Juegos de preguntas (SEED_SET)
├── medios.json          La lista de medios y su inclinación, con la fuente de cada una
└── main.py              Raíz de composición: conecta las capas
```

## Tests

`pytest -q` corre la suite entera en un par de segundos, sin red. Los tests
siguen las mismas capas:

| Carpeta | Qué prueba | Cómo |
| --- | --- | --- |
| `tests/domain/` | LMSR, entidades, políticas (aceptación, censo, encuadre, noticias), la asignación al azar, cuánto apuesta un agente, cada técnica de la nube y la economía del mercado real | Python puro, sin dobles, semillas fijas |
| `tests/application/` | Casos de uso: las tres lecturas del oráculo, qué titular ve cada quien, la dieta de cada agente, qué dieta ganó, el controlador de infraestructura y el mercado real | Oráculo, editor, lectores y nube de ensayo falsos, reloj controlado |
| `tests/adapters/` | Grounding, cada fallo inyectado, dónde pone Vertex el titular, la búsqueda en Google News (atribución, lista, enlaces), que el editor solo elija por número, la Admin API de Cloud Run y el catálogo de precios | Payloads grabados, transporte HTTP simulado y SKUs reales en `fixtures/` |
| `tests/entrypoints/` | La API de punta a punta, incluidas `/api/infra`, las noticias y los juegos de preguntas | `TestClient` con el oráculo simulado y la nube de ensayo |
| `tests/security/` | Cada control de [SECURITY.md](../SECURITY.md) | Recorre las rutas y los archivos estáticos |
| `tests/test_docs.py` | Que [ARQUITECTURA.md](ARQUITECTURA.md) coincida con los `.mmd` y que los enlaces locales de la documentación existan | Sin red |

Otros comandos del [Makefile](../Makefile): `make lint`, `make seguridad` (los
mismos controles que el pipeline), `make lock` (tras cambiar dependencias) y
`make diagramas` (tras editar un `.mmd`).

## Ensayar sin tocar la nube

- **Oráculo simulado.** Sin `GOOGLE_CLOUD_PROJECT`, el oráculo no toca la red y
  devuelve veredictos deterministas. `ORACLE_MOCK_FORCE=YES|NO|UNRESOLVED` fija
  el veredicto.
- **Noticias simuladas.** En el mismo modo, el editor y los agentes usan dos
  medios ficticios (`.example`).
- **Laboratorio rápido.** `SIM_TICK_SECONDS=0.1` cierra una generación en 2,4 s.
- **Encuadre.** Con `SEED_SET=encuadre`, abre dos pestañas privadas con nombres
  distintos: cada una ve un titular.
- **Código de sala.** Aparece en la proyección. Con `SALA_CODIGO=` (vacío) en
  `.env` se entra sin código, solo en local: en producción la API no arranca así.
- **Infraestructura de ensayo.** La nube en memoria se comporta como Cloud Run:
  los cambios tardan un par de ciclos y las fallas se ven en los sondeos.

  ```bash
  SEED_SET=nube_real INFRA_MODE=ensayo INFRA_INTERVALO=2 INFRA_RPS_POR_INSTANCIA=1 \
    uvicorn app.main:app --port 8080
  ```

  Abre `/nube.html`, activa la actuación y deja `/` abierta en otra pestaña para
  generar demanda. `INFRA_MODE=plan` es el paso siguiente: habla con Cloud Run
  de verdad, pero con `validateOnly`.
- **Contenedor.**

  ```bash
  docker build -t oraculo-api:dev .
  docker run -p 8080:8080 -e ORACLE_BACKEND=mock -e SEED_SET=mixta oraculo-api:dev
  ```

En VS Code, F5 arranca la API con recarga y el panel de pruebas descubre la
suite. Todas las variables de entorno, con su explicación, están en
[`.env.example`](../.env.example).

### Conectar Vertex AI en local

```bash
gcloud auth application-default login
gcloud services enable aiplatform.googleapis.com --project TU_PROYECTO
```

Luego pon `GOOGLE_CLOUD_PROJECT=TU_PROYECTO` y `ORACLE_BACKEND=vertex` en `.env`.
No hay llave de API: se usan las credenciales por defecto del entorno (en Cloud
Run, la cuenta de servicio).

## Decisiones de diseño

### El modelo

**El modelo propone, el código dispone.** `AcceptancePolicy` exige confianza
mínima y al menos dos dominios independientes, y falla cerrado ante un error de
red, JSON malformado o un resultado desconocido. `FramingPolicy` añade que el
veredicto no dependa del titular. Un `UNRESOLVED` deja el mercado abierto.

**Una sola ruta de interpretación.** Vertex AI y el simulado devuelven el mismo
formato de `generateContent` y pasan por `run → inject_fault → interpret →
AcceptancePolicy`. No agregues lógica de aceptación en un adaptador: si algo no
está en la ruta común, el ensayo deja de probar lo que se usa en producción.

**La evidencia no la escribe el modelo.** Sale de `groundingMetadata`. Los `uri`
de los grounding chunks son redirecciones que comparten host, así que el dominio
real se lee del campo `domain`. Hay un test que lo fija; no lo borres.

### Las noticias

**Un titular no es evidencia.** Llega al modelo dentro de `<noticia>`, en el
turno del usuario, marcado como dato no confiable. Nunca en la instrucción de
sistema: eso es exactamente el fallo `noticia_como_verdad`.

**Un titular lo publica el medio, no el modelo.** El texto que se muestra de un
medio real viene de Google News, que lo atribuye al medio. El modelo solo elige
titulares por su número.

**La inclinación la decide una fuente publicada.** Cada medio de
[`app/medios.json`](../app/medios.json) cita la suya. Ni el código ni el modelo
clasifican medios.

**El experimento de encuadre no expone a nadie.** La asignación vive en el
mercado y solo salen agregados por grupo. Los titulares no se publican hasta
revelar o resolver.

### El mercado

**Las funciones opcionales de una pregunta son objetos propios.** Un `Market`
puede llevar un `FramingExperiment` (titulares, grupos, revelado) o una
`NewsCoverage` (tema, artículos, lecturas de los agentes, estado «leyendo»), en
vez de seis campos sueltos con validaciones cruzadas.

**Leer no cambia nada.** El grupo de encuadre se asigna al entrar o al crear la
pregunta, nunca al consultar la cuenta. El estado «los agentes están leyendo»
vive en el mercado y se marca dentro de la transacción: dos pedidos a la vez no
leen dos veces.

**El historial de precios está acotado.** Al pasar de 400 puntos se queda con uno
de cada dos, conservando la apertura y el último precio. El número de órdenes se
cuenta aparte.

**El censo no pasa por el oráculo.** Las preguntas `sala` se resuelven con
`CensusPolicy` (mínimo de respuestas). Solo se publica el conteo.

**Los mercados abren en 50 %.** Antes se sembraban órdenes de la casa, pero eso
contaminaba la única afirmación honesta: «el precio se movió».

**Los agentes de noticias no se pueden suplantar.** Se llaman `agente:<dieta>`, y
la audiencia no puede usar «:» en su nombre.

### La operación

**Entrar exige el código de sala.** Lo genera la API al arrancar y solo lo ve
quien modera, en la proyección. Así nadie de fuera puede llenar la sala ni
agotar el límite de entradas.

**Rutas async, casos de uso síncronos.** Las rutas son `async` y llaman a casos
de uso rápidos y en memoria en el mismo hilo que el event loop. Ningún hilo del
pool compite por el lock del repositorio mientras una ruta async lo espera.

**Solo la audiencia autenticada es demanda.** El middleware cuenta como demanda
real una petición con token de usuario que obtuvo respuesta, no cualquier tráfico.

**Cada acción de moderación deja rastro.** Las escrituras con clave de moderación
o con el token de Cloud Scheduler, incluidos los intentos fallidos, escriben una
línea JSON con `"auditoria": true` (sin la clave) que Cloud Logging guarda como
registro estructurado.

**En producción, nada simulado.** `Settings.check` no arranca en Cloud Run sin
Vertex AI e `INFRA_MODE=real`; `MarketService(only_real=True)` rechaza preguntas
del laboratorio y titulares sin enlace; `CloudService(lab=False)` apaga los ticks,
las fallas y el juez simulados, y deja solo las topologías. Los simulados existen
para ensayar en local y para los tests.

**Los umbrales se inyectan.** `config.py` lee el entorno y `main.py` construye
las políticas. El dominio recibe números. La única excepción es
`ORACLE_MOCK_FORCE`, que el simulado lee en cada llamada.

**El estado vive en memoria.** No hay base de datos y el servicio corre con
`max-instances=1`: el mercado dura 40 minutos. Para sobrevivir a un reinicio
bastaría un adaptador de Firestore que implemente `Repository`.

**Nada corre en segundo plano.** El laboratorio calcula en cada petición los
ticks que tocan, hasta 50. El controlador de infraestructura corre un ciclo
dentro de `GET /api/infra` cada 10 s. Así la API usa facturación por petición y
escala a cero.

**Los nodos olvidados son el único gasto que no se apaga solo.** La vigilia
(`POST /api/infra/vigilia`, que Cloud Scheduler llama cada 15 min) los borra si
nadie miró la proyección en `INFRA_TTL_SEGUNDOS`. Un proceso recién arrancado
asume que nadie mira.

**Tres defensas antes de la nube.** `TopologyPolicy` (¿es un buen diseño?),
`ActuationPolicy` (¿se puede ejecutar en esta cuenta?) y el adaptador, que solo
construye nombres `oraculo-nodo-*` y nunca toca un servicio sin
`oraculo-demo=true`.

**Detalles de Google Cloud.** Cloud Run reserva las rutas que terminan en `z`
(`/healthz` da 404 desde Google): usa `/api/salud`. Los modelos gemini-2.5 se
retiran el 20 de octubre de 2026; el default es `gemini-3.8-flash`
(`ORACLE_MODEL`).
