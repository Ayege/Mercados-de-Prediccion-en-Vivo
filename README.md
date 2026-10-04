# Oráculo — mercado de predicción en vivo

Demo para charla: la audiencia opera un mercado de predicción desde el móvil,
los precios son probabilidades, y un oráculo de IA resuelve cada pregunta
buscando en la web. Todo corre en Google Cloud y se despliega con CI/CD.

## Qué hay dentro

| Ruta | Qué contiene |
| --- | --- |
| `app/lmsr.py` | Market maker automático (LMSR de Hanson): costo, precios, acciones por monto |
| `app/market.py` | Motor de mercados: saldos, posiciones, liquidación |
| `app/oracle.py` | Puerto del oráculo, adaptador de Vertex AI y adaptador simulado |
| `app/main.py` | API HTTP y rutas |
| `tests/` | 24 tests: propiedades del LMSR, política de aceptación, API |

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

Abre http://localhost:8080. Sin `GOOGLE_CLOUD_PROJECT` configurado, el oráculo
usa el adaptador simulado: no toca la red y devuelve veredictos deterministas.
Es el modo correcto para ensayar la charla.

En VS Code: F5 arranca la API con recarga, y el panel de pruebas descubre la
suite automáticamente. Las extensiones recomendadas aparecen al abrir la carpeta.

## Conectar Vertex AI de verdad

```bash
gcloud auth application-default login
gcloud services enable aiplatform.googleapis.com --project TU_PROYECTO
```

Luego pon `GOOGLE_CLOUD_PROJECT=TU_PROYECTO` y `ORACLE_BACKEND=vertex` en `.env`.
No hay llave de API: la autenticación usa las credenciales por defecto del
entorno, y en Cloud Run será la identidad de la propia cuenta de servicio.

## Decisiones que conviene conocer antes de tocar el código

**El estado vive en memoria.** No hay base de datos, y el servicio se despliega
con `max-instances=1`. Es deliberado: el mercado dura 40 minutos. Si esto
tuviera que sobrevivir a un reinicio, el siguiente paso sería Firestore.

**El modelo propone, el código dispone.** `apply_policy` decide si un veredicto
se acepta: confianza mínima, al menos dos dominios independientes, y fail-closed
ante error de red, JSON malformado o resultado desconocido. Un `UNRESOLVED` deja
el mercado abierto. Esa función es el corazón del sistema y donde más vale la
pena mirar los tests.

**La evidencia no la escribe el modelo.** Sale de `groundingMetadata`, que
Vertex AI adjunta según lo que realmente buscó. Ojo con un detalle: los `uri`
de los grounding chunks son enlaces de redirección y todos comparten host, así
que el dominio real se lee del campo `domain` y no de la URL. Hay un test que
fija ese comportamiento; no lo borres pensando que es redundante.

**Los modelos gemini-2.5 se retiran el 20 de octubre de 2026.** El default es
`gemini-3.8-flash`, configurable con `ORACLE_MODEL`.

## Contenedor

```bash
docker build -t oraculo-api:dev .
docker run -p 8080:8080 -e ORACLE_BACKEND=mock oraculo-api:dev
```

## Pendiente

- Interfaz de proyección para la charla
- Pipeline de GitHub Actions hacia Cloud Run con identidad federada
