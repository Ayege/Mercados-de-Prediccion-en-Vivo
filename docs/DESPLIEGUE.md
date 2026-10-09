# Despliegue en Google Cloud

Cloud Run, con la imagen construida en Cloud Build y guardada en Artifact
Registry. No hace falta Docker local. Estos comandos son los que crearon el
proyecto `oraculo-6d1578`.

- [Costos](#costos)
- [Una sola vez: proyecto, APIs e identidades](#una-sola-vez-proyecto-apis-e-identidades)
- [Primer despliegue](#primer-despliegue)
- [Publicar cambios](#publicar-cambios)
- [Cambiar las preguntas](#cambiar-las-preguntas)
- [Comprobar](#comprobar)
- [Al terminar una sesión](#al-terminar-una-sesión)

## Costos

| Recurso | Cuándo cobra | Cómo se contiene |
| --- | --- | --- |
| API `oraculo-api` | Solo mientras atiende peticiones | Facturación por petición (`--cpu-throttling`) y escala a cero. Las páginas solo consultan con la pestaña visible, y los móviles piden un resumen sin historial (`/api/markets?resumen=true`) |
| Bucle de infraestructura | Nunca por sí solo | Corre dentro de las consultas del ponente (`/nube.html` o `/proyeccion.html` con la clave), cada 10 s, solo mientras alguna está visible |
| Nodos `oraculo-nodo-*` | Las instancias mínimas cobran aunque nadie las use | ¼ vCPU y 256 MiB; 2 instancias mínimas en total como máximo |
| Agentes `oraculo-agente-*` | Las peticiones que atienden, y la instancia mínima si su gen `warm` está activo | Como mucho 1 agente caliente (0,45 centavos/hora) y 12 peticiones por ciclo (≈ 1 µUSD cada una) |
| Nodos y agentes olvidados | Si la API duerme, siguen ahí | La vigilia los borra a los 30 min sin nadie mirando |
| Gemini | Por llamada, siempre a pedido del ponente | Una topología; una consulta al oráculo (tres con encuadre); una búsqueda de noticias (como máximo una cada 30 s); la opinión de los agentes (cuatro, una vez por pregunta) |
| Imágenes | Almacenamiento | Se conservan las 3 más recientes |
| Todo el proyecto | — | Presupuesto de 10 USD/mes con alertas al 50, 90 y 100 %. **Un presupuesto alerta, no corta** |

**Durante una sesión en vivo, sube a `--min-instances 1`.** Con mínimo 0 y máximo 1, las
peticiones que llegan mientras la instancia arranca en frío reciben un 429 de
Cloud Run. Cuesta unos 1,4 centavos por hora:

```bash
gcloud run services update oraculo-api --region us-east1 --min-instances 1   # antes de empezar
gcloud run services update oraculo-api --region us-east1 --min-instances 0   # al terminar
```

### El estado sobrevive a la escala a cero

Cuando la API duerme, la sala no se pierde: con `ESTADO_BUCKET`, la API guarda una
foto del estado en `gs://$PROJECT_ID-estado` (como mucho una cada 5 s tras un
cambio, y al apagarse) y la restaura al despertar, con el mismo código de sala y
las mismas sesiones de los móviles. La actuación sobre la nube real vuelve
siempre en pausa.

- **Costo:** un solo objeto en us-east1, dentro del nivel gratuito de Cloud
  Storage. El bucket no tiene *soft delete*: si no, cada foto sobrescrita se
  guardaría y cobraría 7 días.
- **Se empieza de cero** si la foto tiene más de `ESTADO_MAX_HORAS` (12), si
  cambió el código de `domain` o `application`, o si cambió `PRESENTER_KEY`, con
  la que se firma.
- **Para vaciar la sala a mano:** `gcloud storage rm gs://$PROJECT_ID-estado/estado/sala.bin`
  y una revisión nueva (`gcloud run services update oraculo-api --region $REGION`).

Una sola vez:

```bash
gcloud storage buckets create gs://$PROJECT_ID-estado --location $REGION \
  --uniform-bucket-level-access --public-access-prevention --soft-delete-duration 0
gcloud storage buckets add-iam-policy-binding gs://$PROJECT_ID-estado \
  --member serviceAccount:oraculo-run@$PROJECT_ID.iam.gserviceaccount.com --role roles/storage.objectUser
```

`cloudbuild.yaml` fija `ESTADO_BUCKET` en cada despliegue.

## Una sola vez: proyecto, APIs e identidades

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
BUILD=oraculo-build@$PROJECT_ID.iam.gserviceaccount.com     # el pipeline: solo publicar y desplegar
gcloud iam service-accounts create oraculo-run --display-name="oraculo-api en Cloud Run"
gcloud iam service-accounts create oraculo-nodo --display-name="Nodos reales (sin roles)"
gcloud iam service-accounts create oraculo-vigilia --display-name="Cloud Scheduler: vigilia (sin roles)"
gcloud iam service-accounts create oraculo-build --display-name="Cloud Build: pipeline (permisos mínimos)"

# La clave de ponente vive en Secret Manager, legible solo por oraculo-run.
openssl rand -hex 16 | tr -d '\n' | gcloud secrets create oraculo-presenter-key \
  --replication-policy=user-managed --locations=$REGION --data-file=-
gcloud secrets add-iam-policy-binding oraculo-presenter-key \
  --member="serviceAccount:$RUN" --role=roles/secretmanager.secretAccessor

gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$RUN" \
  --role=roles/aiplatform.user --condition=None
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$RUN" \
  --role=roles/run.invoker --condition=None
# run.developer con condición: crear y modificar solo oraculo-nodo-* y oraculo-agente-*.
# Listar se permite porque su recurso es la ubicación, no un servicio.
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$RUN" --role=roles/run.developer \
  --condition='title=solo-servicios-de-la-demo,expression=resource.name.extract("/services/{s}") == "" || resource.name.extract("/services/{s}").startsWith("oraculo-nodo-") || resource.name.extract("/services/{s}").startsWith("oraculo-agente-")'

# Desplegar nodos que corren como oraculo-nodo, con la imagen del repositorio:
gcloud iam service-accounts add-iam-policy-binding $NODO --member="serviceAccount:$RUN" \
  --role=roles/iam.serviceAccountUser
gcloud artifacts repositories add-iam-policy-binding oraculo --location=$REGION \
  --member="serviceAccount:$RUN" --role=roles/artifactregistry.reader

# El pipeline corre como oraculo-build (lo fija cloudbuild.yaml), nunca como la cuenta de
# Compute por defecto, que en muchos proyectos tiene Editor sobre todo.
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$BUILD" \
  --role=roles/logging.logWriter --condition=None
gcloud artifacts repositories add-iam-policy-binding oraculo --location=$REGION \
  --member="serviceAccount:$BUILD" --role=roles/artifactregistry.writer
gcloud iam service-accounts add-iam-policy-binding $RUN --member="serviceAccount:$BUILD" \
  --role=roles/iam.serviceAccountUser
gcloud storage buckets add-iam-policy-binding gs://${PROJECT_ID}_cloudbuild \
  --member="serviceAccount:$BUILD" --role=roles/storage.objectViewer
# Tras el primer despliegue (abajo): run.developer solo sobre oraculo-api.

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

| Permiso | Para qué |
| --- | --- |
| `run.developer`, con condición, para `oraculo-run` | Crear y modificar solo servicios `oraculo-nodo-*` y `oraculo-agente-*` (verificado: modificar `oraculo-api` o crear otro servicio da 403). No incluye cambiar permisos IAM, así que no pueden volverse públicos. Límite: Cloud Run no informa el nombre del servicio al revisar lecturas y borrados, así que la condición no los restringe |
| `run.invoker` | Sondear los nodos, que son privados, con un token de identidad |
| `serviceAccountUser`, solo sobre `oraculo-nodo` | Desplegar nodos que corren sin roles |
| `artifactregistry.reader`, solo sobre el repositorio | Cloud Run comprueba que quien despliega pueda leer la imagen; sin él, crear un nodo da 403 |
| `secretAccessor`, solo sobre `oraculo-presenter-key` | Que la API lea su clave y ningún otro secreto |
| `oraculo-vigilia`, sin roles | Solo firma el token OIDC con el que Cloud Scheduler se presenta |
| `oraculo-build`: `artifactregistry.writer` en el repositorio, `run.developer` solo en `oraculo-api`, `serviceAccountUser` solo sobre `oraculo-run`, lectura del bucket de fuentes y `logWriter` | Publicar la imagen y desplegar la API. Si una herramienta del pipeline estuviera comprometida, no alcanza al resto del proyecto |

Comprueba que la cuenta de Compute por defecto no tenga `roles/editor`: si el
proyecto se la dio al crearse, quítasela.

## Primer despliegue

Es a mano, porque define la identidad, el secreto y las variables:

```bash
IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/oraculo/oraculo-api:inicial
gcloud builds submit --tag $IMAGE

gcloud run deploy oraculo-api --image $IMAGE --region $REGION --service-account $RUN \
  --allow-unauthenticated --cpu-throttling --min-instances 0 --max-instances 1 \
  --concurrency 250 --cpu 1 --memory 512Mi \
  --set-secrets PRESENTER_KEY=oraculo-presenter-key:latest \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT_ID,ORACLE_BACKEND=vertex,VERTEX_LOCATION=global,\
SEED_SET=real,INFRA_MODE=real,NODO_IMAGEN=$IMAGE,NODO_CUENTA=$NODO"
gcloud run services add-iam-policy-binding oraculo-api --region $REGION \
  --member="serviceAccount:$BUILD" --role=roles/run.developer

URL=$(gcloud run services describe oraculo-api --region $REGION --format='value(status.url)')
gcloud run services update oraculo-api --region $REGION \
  --update-env-vars "VIGILIA_CUENTA=$VIG,VIGILIA_AUDIENCIA=$URL/api/infra/vigilia"
gcloud scheduler jobs create http oraculo-vigilia --location=$REGION --schedule="*/15 * * * *" \
  --uri="$URL/api/infra/vigilia" --http-method=POST \
  --oidc-service-account-email=$VIG --oidc-token-audience="$URL/api/infra/vigilia"
```

- `--max-instances 1`: el estado vive en memoria; con dos instancias habría dos
  mercados.
- `--set-secrets`: la clave nunca aparece como variable legible en la consola.
- En Cloud Run la API **se niega a arrancar** sin una clave de al menos 32
  caracteres o sin código de sala, y cierra `/api/docs`.
- **En Cloud Run todo es real**, y la API se niega a arrancar si algo no lo es:
  exige `ORACLE_BACKEND=vertex` con proyecto (oráculo, editor y agentes de
  noticias con Gemini), `INFRA_MODE=real` y solo preguntas reales (por defecto, `SEED_SET=real`). El
  laboratorio simulado de `/nube.html` queda apagado.
- El código de sala (`SALA_CODIGO`) se genera solo al arrancar cada revisión y
  aparece en la proyección de quien modera. Para fijarlo, pon un valor propio.
- `INFRA_MODE=plan` es un buen primer paso: Cloud Run valida cada acción y no
  crea nada.

## Publicar cambios

Cada publicación pasa por [`cloudbuild.yaml`](../cloudbuild.yaml), una cadena de
compuertas: secretos (gitleaks) → ruff con bandit → `pip-audit` → toda la suite →
imagen → Trivy → publicar → desplegar. Si una falla, nada llega a producción. El
despliegue cambia la imagen de la API, `NODO_IMAGEN`, `SEED_SET` y `ESTADO_BUCKET`,
y conserva el resto de la configuración.

```bash
gcloud builds submit --config cloudbuild.yaml --region $REGION --project $PROJECT_ID
```

Pasa `--project` siempre: si gcloud tiene otro proyecto configurado por defecto,
el build se iría a ese. Cada publicación fija también `SEED_SET` (por defecto,
`real`); para empezar con la sala vacía, añade `--substitutions=_SEED_SET=ninguna`.

Las imágenes del pipeline van fijadas por digest y las dependencias de Python por
hash. Para actualizarlas:

- **Dependencias:** cambia `requirements.txt` o `requirements-dev.txt` y corre
  `make lock`. El lock de desarrollo respeta las versiones de producción.
- **Imágenes:** consulta el digest nuevo de la etiqueta (por ejemplo, con
  `docker buildx imagetools inspect aquasec/trivy:0.57.1`) y cámbialo en
  `cloudbuild.yaml`, en un commit propio.

**Cada push a `master` publica.** El trigger `oraculo-main` usa una conexión de
GitHub de segunda generación (`oraculo-github`, en us-east1) y corre como
`oraculo-build`. Para montarlo de nuevo:

```bash
# 1. La conexión. El agente de Cloud Build necesita crear el secreto con el token de GitHub:
P4SA=service-$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')@gcp-sa-cloudbuild.iam.gserviceaccount.com
gcloud projects add-iam-policy-binding $PROJECT_ID --member serviceAccount:$P4SA --role roles/secretmanager.admin
gcloud builds connections create github oraculo-github --region $REGION
# Abre el enlace que imprime, autoriza Cloud Build e instala su app en el repositorio.
# 2. Quita el permiso amplio: se queda con acceso solo a su propio secreto.
gcloud projects remove-iam-policy-binding $PROJECT_ID --member serviceAccount:$P4SA --role roles/secretmanager.admin
# 3. El repositorio y el trigger.
gcloud builds repositories create oraculo --connection oraculo-github --region $REGION \
  --remote-uri https://github.com/Ayege/Mercados-de-Prediccion-en-Vivo.git
gcloud builds triggers create github --name oraculo-main --region $REGION \
  --repository projects/$PROJECT_ID/locations/$REGION/connections/oraculo-github/repositories/oraculo \
  --branch-pattern '^master$' --build-config cloudbuild.yaml \
  --service-account projects/$PROJECT_ID/serviceAccounts/oraculo-build@$PROJECT_ID.iam.gserviceaccount.com
```

## Cambiar las preguntas

Para cambiar las preguntas sin publicar código nuevo, cambia `SEED_SET` y vacía
la foto del estado (si no, la revisión nueva restaura la sala anterior). Se
vuelven a sembrar al arrancar, así que **se pierden los mercados abiertos** y
cambia el código de sala. Los juegos están en
[PREGUNTAS.md](PREGUNTAS.md#juegos-de-preguntas).

```bash
gcloud storage rm gs://$PROJECT_ID-estado/estado/sala.bin
gcloud run services update oraculo-api --region $REGION --update-env-vars SEED_SET=real
```

## Comprobar

```bash
curl $URL/api/salud     # {"ok":true}
curl $URL/api/info      # "oracle":"vertex"
curl -sI $URL/ | grep -i content-security-policy
PRESENTER_KEY=$(gcloud secrets versions access latest --secret=oraculo-presenter-key)
echo "Audiencia:  $URL"
echo "Proyección: $URL/proyeccion.html#clave=$PRESENTER_KEY"
echo "Nube:       $URL/nube.html#clave=$PRESENTER_KEY"
```

## Al terminar una sesión

En `/nube.html`, **Apagar todo** borra nodos y agentes. Si te olvidas, la
vigilia los borra a los 30 minutos. Para comprobar que no quedó nada:

```bash
# Sin --region lista todas las regiones (--region=- da error en gcloud 490).
gcloud run services list --filter="metadata.labels.oraculo-demo=true"
# borrar a mano lo que haya quedado:
for s in $(gcloud run services list --filter="metadata.labels.oraculo-demo=true" \
           --format="csv[no-heading](metadata.name,region)"); do
  gcloud run services delete ${s%,*} --region=${s#*,} --quiet
done
```

Cambia la clave de moderación, porque queda en el historial del navegador que
proyectó:

```bash
openssl rand -hex 16 | tr -d '\n' | gcloud secrets versions add oraculo-presenter-key --data-file=-
gcloud run services update oraculo-api --region $REGION   # nueva revisión: lee la versión nueva
```

Para borrarlo todo (se puede recuperar durante 30 días):
`gcloud projects delete $PROJECT_ID`.
