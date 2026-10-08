# Despliegue en Google Cloud

Cloud Run, con la imagen construida en Cloud Build y guardada en Artifact
Registry. No hace falta Docker local. Estos comandos son los que crearon el
proyecto `oraculo-6d1578`.

- [Costos](#costos)
- [Una sola vez: proyecto, APIs e identidades](#una-sola-vez-proyecto-apis-e-identidades)
- [Primer despliegue](#primer-despliegue)
- [Publicar cambios](#publicar-cambios)
- [Cambiar de charla](#cambiar-de-charla)
- [Comprobar](#comprobar)
- [Después de la charla](#después-de-la-charla)

## Costos

| Recurso | Cuándo cobra | Cómo se contiene |
| --- | --- | --- |
| API `oraculo-api` | Solo mientras atiende peticiones | Facturación por petición (`--cpu-throttling`) y escala a cero |
| Bucle de infraestructura | Nunca por sí solo | Corre dentro de las consultas de `/nube.html`, cada 10 s, solo mientras alguien mira |
| Nodos `oraculo-nodo-*` | Las instancias mínimas cobran aunque nadie las use | ¼ vCPU y 256 MiB; 2 instancias mínimas en total como máximo |
| Agentes `oraculo-agente-*` | Las peticiones que atienden, y la instancia mínima si su gen `warm` está activo | Como mucho 1 agente caliente (0,45 centavos/hora) y 12 peticiones por ciclo (≈ 1 µUSD cada una) |
| Nodos y agentes olvidados | Si la API duerme, siguen ahí | La vigilia los borra a los 30 min sin nadie mirando |
| Gemini | Por llamada, siempre a pedido del ponente | Una topología; una consulta al oráculo (tres con encuadre); una búsqueda de noticias (como máximo una cada 30 s); la opinión de los agentes (cuatro, una vez por pregunta) |
| Imágenes | Almacenamiento | Se conservan las 3 más recientes |
| Todo el proyecto | — | Presupuesto de 10 USD/mes con alertas al 50, 90 y 100 %. **Un presupuesto alerta, no corta** |

**Durante la charla, sube a `--min-instances 1`.** Con mínimo 0 y máximo 1, las
peticiones que llegan mientras la instancia arranca en frío reciben un 429 de
Cloud Run. Cuesta unos 1,4 centavos por hora:

```bash
gcloud run services update oraculo-api --region us-east1 --min-instances 1   # antes de empezar
gcloud run services update oraculo-api --region us-east1 --min-instances 0   # al terminar
```

Con la escala a cero, el estado del mercado se pierde cuando la API duerme. En
una charla no pasa, porque los móviles la mantienen despierta.

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

| Permiso | Para qué |
| --- | --- |
| `run.developer` | Crear, escalar y borrar nodos. No incluye cambiar permisos IAM de servicios, así que los nodos no pueden volverse públicos |
| `run.invoker` | Sondear los nodos, que son privados, con un token de identidad |
| `serviceAccountUser`, solo sobre `oraculo-nodo` | Desplegar nodos que corren sin roles |
| `artifactregistry.reader`, solo sobre el repositorio | Cloud Run comprueba que quien despliega pueda leer la imagen; sin él, crear un nodo da 403 |
| `secretAccessor`, solo sobre `oraculo-presenter-key` | Que la API lea su clave y ningún otro secreto |
| `oraculo-vigilia`, sin roles | Solo firma el token OIDC con el que Cloud Scheduler se presenta |

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
SEED_SET=encuadre+nube_real,SIM_SEED=7,INFRA_MODE=real,NODO_IMAGEN=$IMAGE,NODO_CUENTA=$NODO"

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
  caracteres, y cierra `/api/docs`.
- `INFRA_MODE=plan` es un buen primer paso: Cloud Run valida cada acción y no
  crea nada.

## Publicar cambios

Cada publicación pasa por [`cloudbuild.yaml`](../cloudbuild.yaml), una cadena de
compuertas: secretos (gitleaks) → ruff con bandit → `pip-audit` → toda la suite →
imagen → Trivy → publicar → desplegar. Si una falla, nada llega a producción. El
despliegue cambia la imagen de la API y `NODO_IMAGEN`, y conserva el resto de la
configuración.

```bash
gcloud builds submit --config cloudbuild.yaml --region $REGION --project $PROJECT_ID
```

Pasa `--project` siempre: si gcloud tiene otro proyecto configurado por defecto,
el build se iría a ese.

Para que corra en cada push, conecta el repositorio de GitHub en la consola
(Cloud Build → Repositorios) y crea el trigger. Ajusta `--branch-pattern` a la
rama que de verdad publicas (hoy, `master`):

```bash
gcloud builds triggers create github --name=oraculo-main \
  --repo-owner=TU_USUARIO --repo-name=oraculo \
  --branch-pattern='^master$' --build-config=cloudbuild.yaml
```

## Cambiar de charla

Para cambiar las preguntas sin publicar código nuevo, cambia `SEED_SET`. Las
preguntas se vuelven a sembrar al arrancar la nueva revisión, así que **se
pierden los mercados abiertos**. Los juegos están en
[CHARLA.md](CHARLA.md#elegir-las-preguntas).

```bash
gcloud run services update oraculo-api --region $REGION --update-env-vars SEED_SET=encuadre+nube_real
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

## Después de la charla

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

Cambia la clave de ponente, porque queda en el historial del navegador que
proyectó:

```bash
openssl rand -hex 16 | tr -d '\n' | gcloud secrets versions add oraculo-presenter-key --data-file=-
gcloud run services update oraculo-api --region $REGION   # nueva revisión: lee la versión nueva
```

Para borrarlo todo (se puede recuperar durante 30 días):
`gcloud projects delete $PROJECT_ID`.
