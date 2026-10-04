# Oráculo — mercado de predicción en vivo

Demo para charla. La audiencia opera un mercado de predicción desde el móvil y
los precios son probabilidades. Un oráculo de IA intenta resolver cada pregunta
buscando en la web, y el código decide si acepta su veredicto. Todo corre en
Google Cloud.

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

## Qué hay dentro

El código sigue clean architecture: las dependencias apuntan hacia adentro y el
centro no sabe que existen FastAPI, Vertex AI ni la memoria del proceso.

```
app/
├── domain/              Reglas puras. No importa nada del proyecto ni de I/O.
│   ├── lmsr.py          Market maker automático (LMSR de Hanson)
│   ├── market.py        Entidades Market y Account: órdenes, censo, liquidación
│   ├── verdict.py       Verdict, AcceptancePolicy y CensusPolicy
│   └── errors.py
├── application/         Casos de uso y los puertos que necesitan.
│   ├── service.py       MarketService: crear, operar, censo, resolver
│   ├── ports.py         OracleGateway, Repository y el catálogo de fallos
│   ├── views.py         Lo que sale de un caso de uso (dicts planos)
│   └── errors.py        NotFound, Cooldown
├── adapters/            Implementaciones de los puertos.
│   ├── memory.py        Repository en memoria, con lock
│   └── oracle/
│       ├── gemini.py    Ruta común: run → inject_fault → interpret → política
│       ├── vertex.py    Gemini en Vertex AI con grounding
│       └── mock.py      Simulado, con la misma forma de respuesta
├── entrypoints/http/    FastAPI: rutas, esquemas, clave de ponente y estáticos
│   └── static/          index.html (audiencia) y proyeccion.html (proyección)
├── config.py            Settings: el único que lee el entorno
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
| `tests/domain/` | LMSR, entidades, políticas | Python puro, sin dobles |
| `tests/application/` | Casos de uso | Oráculo falso y reloj controlado |
| `tests/adapters/` | Lectura de grounding, cada fallo inyectado | Payloads de `generateContent` |
| `tests/entrypoints/` | API de punta a punta | `TestClient` con el oráculo simulado |

## Arranque local

Requiere Python 3.12 o superior.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env

pytest -q
uvicorn app.main:app --reload --port 8080
```

- Audiencia: http://localhost:8080
- Proyección: http://localhost:8080/proyeccion.html

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

**Los modelos gemini-2.5 se retiran el 20 de octubre de 2026.** El default es
`gemini-3.8-flash`, configurable con `ORACLE_MODEL`.

## Contenedor

```bash
docker build -t oraculo-api:dev .
docker run -p 8080:8080 -e ORACLE_BACKEND=mock -e SEED_SET=mixta oraculo-api:dev
```

## Publicar en Google Cloud

Cloud Run, con la imagen construida en Cloud Build y guardada en Artifact
Registry. No hace falta Docker local. Haz commit antes de publicar: la imagen
se etiqueta con el SHA.

### Una sola vez: proyecto, APIs e identidad

```bash
export PROJECT_ID=oraculo-charla-$(openssl rand -hex 3)   # único en todo Google Cloud
export REGION=us-east1                                     # la más cercana a Santo Domingo
export BILLING=$(gcloud billing accounts list --filter=open=true --format='value(name)' --limit=1)

gcloud projects create $PROJECT_ID --name="Oraculo charla"
gcloud billing projects link $PROJECT_ID --billing-account=$BILLING
gcloud config set project $PROJECT_ID

gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com

gcloud artifacts repositories create oraculo --repository-format=docker --location=$REGION

# Identidad del servicio: solo puede llamar a Vertex AI.
gcloud iam service-accounts create oraculo-run --display-name="oraculo-api en Cloud Run"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:oraculo-run@$PROJECT_ID.iam.gserviceaccount.com" \
  --role=roles/aiplatform.user

# En proyectos nuevos, Cloud Build construye con la cuenta de Compute y necesita este rol.
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role=roles/cloudbuild.builds.builder
```

### Cada publicación: construir y desplegar

```bash
export PROJECT_ID=...   REGION=us-east1          # los mismos de arriba
export PRESENTER_KEY=$(openssl rand -hex 16)      # guárdala: es tu acceso de ponente
IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/oraculo/oraculo-api:$(git rev-parse --short HEAD)

gcloud builds submit --tag $IMAGE

gcloud run deploy oraculo-api --image $IMAGE --region $REGION \
  --service-account oraculo-run@$PROJECT_ID.iam.gserviceaccount.com \
  --allow-unauthenticated \
  --min-instances 1 --max-instances 1 --concurrency 250 --cpu 1 --memory 512Mi \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT_ID,ORACLE_BACKEND=vertex,VERTEX_LOCATION=global,SEED_SET=oraculo,PRESENTER_KEY=$PRESENTER_KEY
```

Por qué cada bandera:

- `--min-instances 1 --max-instances 1`: el estado vive en memoria. Con dos
  instancias, cada una tendría su propio mercado. Con cero, Cloud Run apagaría
  la instancia en una pausa y el mercado se perdería.
- `--concurrency 250`: ochenta móviles que consultan cada 3 s, más la
  proyección, caben con holgura en una instancia.
- `--allow-unauthenticated`: la audiencia entra sin cuenta. Lo que está
  protegido (crear y resolver mercados) lo cubre `PRESENTER_KEY`.

### Comprobar

```bash
URL=$(gcloud run services describe oraculo-api --region $REGION --format='value(status.url)')
curl $URL/healthz                 # {"ok":true}
curl $URL/api/info                # "oracle":"vertex" y presenter_key_required: true
echo "Audiencia:  $URL"
echo "Proyección: $URL/proyeccion.html#clave=$PRESENTER_KEY"
```

Antes de la charla, consulta al oráculo una vez sobre la pregunta `futuro` y
confirma que responde con fuentes reales. Así sabes que Vertex AI y los
permisos funcionan.

### Después de la charla

`--min-instances 1` cobra aunque nadie use el servicio. Cuando termines:

```bash
gcloud run services update oraculo-api --region $REGION --min-instances 0
# o, para borrarlo todo (se puede recuperar durante 30 días):
gcloud projects delete $PROJECT_ID
```

`PRESENTER_KEY` es una variable de entorno, así que la ve cualquiera con
acceso de lectura al proyecto. En un proyecto personal es suficiente. Si
compartes el proyecto, muévela a Secret Manager (`--set-secrets`).

## Pendiente

- Pipeline de GitHub Actions hacia Cloud Run con identidad federada

## Diagramas

`docs/` contiene los cuatro diagramas C4 en Mermaid: contexto, contenedores,
componentes y despliegue. GitHub solo los renderiza si están dentro de un bloque
```mermaid en un archivo Markdown. Para verlos en VS Code, instala la extensión
Markdown Preview Mermaid Support o pégalos en mermaid.live.
