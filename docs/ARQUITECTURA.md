# Arquitectura

Cómo está construido Oráculo, de afuera hacia adentro: contexto, contenedores,
componentes y despliegue (modelo C4), dos flujos clave y las fronteras de
confianza. Para *por qué* existe la demo y qué afirmar con ella, ver el
[README](../README.md); para las amenazas y los controles, ver
[SECURITY.md](../SECURITY.md).

Los diagramas viven en `docs/*.mmd`, que son la fuente de verdad. Este documento
los copia en bloques `mermaid`, que GitHub renderiza solo. Si editas un `.mmd`,
corre `make diagramas`: `tests/test_docs.py` falla si este documento quedó viejo.

## 1. Contexto

Quién usa el sistema y de qué sistemas externos depende.

![Diagrama de contexto](c4-nivel1-contexto.png)

[Abrir y editar en mermaid.live](https://mermaid.live/edit#pako:eNqNVn9v2zYQ_SoHFwUWTE7ixMkMLwjgOl0WLL8QZ8WAqn-cyJPDlSJVUvTmFf3uO4qSnSzpEBiwLd7du8fju6O-DoSVNJjCYDgc5qZRjaYp5INrtSINI8jDwf5oDHNrGvq7sVOoyAmUFiRB7UgqIVQe9vfLQwNrMKEgwNB0K7bCfJCbFvntWzhTuHRYYYwVHSDMxyBVEf6MmMJWFkpt_xIP6JopMAONaxua6GWwUas27xW5CpVsMbFiIGuQHT1Qo74EatDvMmFtHXkOnEJNzkeXH_CfoMF6EZzdycAr3xCzqZ2tlU3WnaxF7U3MkJxh29Ipv7Obmw05uLzLDUAdCq2E_cjbDHJyKPlbHB_BSXE6C1KREardrUaIURpP9orTk8LtnZ6o04-3idenkz2VFmd1IN_ECM9BvPsqFXKldCwYBAON_Uymo7zbBi0CNC760ahkKsCb1hGiQiMRHKHezQefWrLWEFe9Jyv4u8RxJHubLP_P7obriB22bfnEbWlcUSuGBJFyxWzWoQg6loYT3HQM48qTLItU6W2Wq05fl1eLu4xBtnExy8XsRZWlSrzngrGY2TPWh_n8DNJ6ZqZbENkoEUViQKRIqZYRVChJZst7RY6VmWh_aP_D7OIlzr06ttzPqVJGTSNE7IyGk8cyLZ0NRiqzbJ3WLbv2oH3cUsNUtV0mitifVRliNX2i8Ut64EBVoVPoX0fnjjShJ59BgUZEMgzjUPNKa3e05FDHBsvKUdHQpxfaBumCSfnn8Qnugnld3msby96d_9Dw0_Du_flF3KE8vAZuUdZ26xmngLOaz9uBYKlmrF6Bmn8d1chqW0NhndtUxRN7cVkTrUX7BFdocEnulUcU0En8vnI5h3ggGTS5x3tf9Iuvy_JBLZXm1mclI4yOgGXRNXBrTk18c3E2h1LxLGO511yBc2uXesOjCErLxxzexYXX5Z_bihXmWGHTTc1aFUjVpLOvVT3EEB9ZVYEKZPu9U6v1thG62QbDId8H_Wha88l4rliaTywob3s6v97f3y7gR_hj-LsnN7yPm4yM8gFDnPZ6eDSIEvKTsfIc65bzRWc3_I3WL8N1fxMc-y-DaZnW6ll7-ScJMpidzR9hptbfDoGE-C6wJoFWcUxwl_QI267eAnRd-4zUTEYFzG4vYHXAxHysn91wYRJZGuztQIh5GiVRPgLu-_EZ8iXRVsyoAblbjEDXxfWH_0TYXaFuFvewh7XaU6Z0uLdKmu1JRXW-XO5WmAnjjLWgFS2Rb0zeQdQxevxvSBoo6P0ZlZvLuFRaT9_sT8YHPxVZnEKfiR-PDujoOBPx8p6-KcvySWh_K6fQ0eh4UshtaDGeTMbfC-0v8hQ6EfGzCT0u4uel0L4Hsl6xHfutQ38YHbetISko6xSR9QeYbdpxcxxZKmhHMTeDDAZVesWJ72Vf80HzQBXlg_heJqnEoJt88C268SVoF2sj2NRwF_NKqCU21L1pdcvf_gU6QlzC) · [SVG](c4-nivel1-contexto.svg) · [fuente](c4-nivel1-contexto.mmd)

<details>
<summary>Fuente Mermaid del diagrama de contexto</summary>

<!-- mmd:c4-nivel1-contexto -->
```mermaid
---
title: "Nivel 1 — Contexto: mercado de predicción y nube autónoma"
---
%% Diagrama de contexto C4 dibujado como flowchart: el layout C4 nativo de Mermaid
%% amontona las etiquetas. Colores C4: persona (azul oscuro), sistema propio (azul),
%% sistema externo (gris).
flowchart LR
  publico["👥 <b>Audiencia de la charla</b><br/><i>[Persona]</i><br/>Apuesta desde el móvil con un token propio.<br/>Su tráfico es la demanda real."]
  ponente["🎤 <b>Ponente</b><br/><i>[Persona]</i><br/>Opera la demo con la clave de ponente."]

  oraculo["<b>Oráculo</b><br/><i>[Sistema]</i><br/>Mercado LMSR, oráculo de IA y nube autónoma.<br/>El modelo propone; dos políticas en código deciden."]

  vertex["<b>Vertex AI</b><br/><i>[Sistema externo]</i><br/>Gemini: veredictos con grounding<br/>y propuestas de topología."]
  fuentes["<b>Fuentes primarias</b><br/><i>[Sistema externo]</i><br/>Releases, bancos centrales,<br/>registros oficiales."]
  cloudrun["<b>Cloud Run</b><br/><i>[Sistema externo]</i><br/>Nodos oraculo-nodo-REGIÓN que el<br/>controlador crea, escala, repara y borra."]
  secretos["<b>Secret Manager</b><br/><i>[Sistema externo]</i><br/>Guarda la clave de ponente."]
  scheduler["<b>Cloud Scheduler</b><br/><i>[Sistema externo]</i><br/>Vigilia cada 15 min con un<br/>token OIDC firmado por Google."]
  build["<b>Cloud Build</b><br/><i>[Sistema externo]</i><br/>Compuertas: secretos, bandit,<br/>pip-audit, pruebas, Trivy."]

  publico -- "Apuesta y responde el censo<br/><i>HTTPS + X-User-Token</i>" --> oraculo
  ponente -- "Opera la demo<br/><i>HTTPS + X-Presenter-Key</i>" --> oraculo
  oraculo -- "Pregunta y pide topologías<br/><i>HTTPS, ADC</i>" --> vertex
  vertex -- "Busca evidencia<br/><i>grounding</i>" --> fuentes
  oraculo -- "Admin API v2 y sondeos<br/><i>ADC, tokens de identidad</i>" --> cloudrun
  oraculo -- "Lee la clave al arrancar" --> secretos
  scheduler -- "POST /api/infra/vigilia<br/><i>OIDC</i>" --> oraculo
  build -- "Despliega si todo pasa" --> oraculo

  classDef persona fill:#08427b,stroke:#052e56,color:#fff
  classDef sistema fill:#1168bd,stroke:#0b4884,color:#fff
  classDef externo fill:#8c8c8c,stroke:#6b6b6b,color:#fff
  class publico,ponente persona
  class oraculo sistema
  class vertex,fuentes,cloudrun,secretos,scheduler,build externo
```
<!-- /mmd -->

</details>

Lo esencial está en el centro: **el modelo propone y el código dispone**.
Gemini propone veredictos y topologías; nada llega a la audiencia ni a Cloud
Run sin pasar por una política escrita en Python.

## 2. Contenedores

Qué se ejecuta, dónde y cómo se habla. Todo vive en un proyecto de Google Cloud
(`oraculo-6d1578`, `us-east1`).

<!-- mmd:c4-nivel2-contenedores -->
```mermaid
C4Container
  title Nivel 2 — Contenedores en Google Cloud (proyecto oraculo-6d1578)

  Person(publico, "Audiencia de la charla")
  Person(ponente, "Ponente")

  Container_Boundary(sistema, "Proyecto de Google Cloud") {
    Container(web, "Pantallas", "HTML y JavaScript sin scripts en línea", "/, /proyeccion.html, /nube.html; CSP script-src 'self'")
    Container(api, "oraculo-api", "FastAPI en Cloud Run", "Controles de borde, mercado, simulación y controlador; escala a cero, máximo 1")
    ContainerDb(estado, "Estado", "Memoria del proceso", "Mercados, cuentas (solo hashes de tokens) y simulación")
    Container(nodos, "oraculo-nodo-<región>", "Cloud Run privado, ¼ vCPU", "Solo /salud; corren como oraculo-nodo, sin roles")
    ContainerDb(secreto, "Secret Manager", "oraculo-presenter-key", "Solo oraculo-run puede leerlo")
    Container_Ext(scheduler, "Cloud Scheduler", "Job oraculo-vigilia", "Firma con la cuenta oraculo-vigilia, sin roles")
    Container_Ext(registry, "Artifact Registry", "Imágenes OCI", "Solo imágenes que pasaron Trivy; se conservan 3")
  }

  System_Ext(vertex, "Vertex AI", "Gemini")

  Rel(publico, web, "Apuesta; su tráfico es la demanda", "HTTPS + token de usuario")
  Rel(ponente, web, "Controla", "HTTPS + clave de ponente")
  Rel(web, api, "Llama", "JSON, mismo origen")
  Rel(api, estado, "Lee y escribe", "en proceso")
  Rel(api, secreto, "PRESENTER_KEY", "secretAccessor")
  Rel(api, vertex, "Veredictos y topologías", "ADC, sin llaves")
  Rel(api, nodos, "Crea, escala, repara, borra; sondea", "Admin API v2, token de identidad")
  Rel(scheduler, api, "Vigilia", "OIDC verificado por la app")
  Rel(registry, nodos, "Imagen")
  Rel(registry, api, "Imagen")

  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```
<!-- /mmd -->

| Contenedor | Por qué así |
| --- | --- |
| `oraculo-api` | Una sola instancia (`max 1`) porque el estado vive en memoria; escala a cero y cobra por petición |
| `oraculo-nodo-<región>` | La misma imagen con `APP_MODULE=app.node:app`; privados (requieren token de identidad); ¼ de vCPU |
| Secret Manager | La única credencial propia es la clave de ponente; todo lo demás usa identidades de Google (ADC, OIDC) |
| Cloud Scheduler | La vigilia: el único gasto que no se apaga solo son los nodos olvidados |

## 3. Componentes de `oraculo-api`

Clean architecture: las dependencias apuntan hacia adentro y
`tests/test_architecture.py` lo verifica en cada commit.

<!-- mmd:c4-nivel3-componentes -->
```mermaid
C4Component
  title Nivel 3 — Componentes de oraculo-api (clean architecture)

  Container_Boundary(api, "oraculo-api (FastAPI)") {
    Component(http, "Entrypoint HTTP", "entrypoints/http/api.py", "Rutas y controles de borde: clave de ponente, token de usuario, OIDC, CSP y cabeceras")
    Component(esquemas, "Esquemas", "entrypoints/http/schemas.py", "Pydantic: longitudes, patrones de nombre y región")
    Component(limites, "Límites de abuso", "application/limits.py", "Ventana deslizante: órdenes por persona y entradas por minuto")
    Component(raiz, "Raíz de composición", "main.py · config.py · seeds.py", "Lee el entorno y conecta las capas")
    Component(servicio, "Casos de uso", "application/service.py", "Entrar, operar, censo, resolver; autentica con hash del token")
    Component(puertos, "Puertos", "application/ports.py", "OracleGateway, Repository y catálogo de fallos")
    Component(dominio, "Dominio", "domain/", "Market, Account, LMSR, AcceptancePolicy, CensusPolicy")
    Component(memoria, "Repositorio en memoria", "adapters/memory.py", "Implementa Repository con un lock")
    Component(ruta, "Ruta común Gemini", "adapters/oracle/gemini.py", "run · inject_fault · interpret")
    Component(vertexad, "Adaptador Vertex AI", "adapters/oracle/vertex.py", "generateContent con grounding")
    Component(mock, "Adaptador simulado", "adapters/oracle/mock.py", "Payload con la misma forma, sin red")
    Component(nube, "Caso de uso de la nube", "application/cloud.py", "Avance perezoso por reloj, fallas, topologías, juez")
    Component(sim, "Nube simulada", "domain/cloud/", "Holt-Winters, Q-learning, Shapley, GA, EWMA, TopologyPolicy")
    Component(gentopo, "Generadores de topologías", "adapters/topology/", "Gemini y simulado; ninguno decide")
    Component(infra, "Controlador de infraestructura", "application/infra.py", "Observa, predice con Holt, sondea, repara; corre dentro de GET /api/infra")
    Component(actuacion, "ActuationPolicy", "domain/cloud/infra.py", "Regiones, topes de instancias, ritmo de cambios; recorta y revisa")
    Component(gwrun, "Adaptador Cloud Run", "adapters/infra/cloudrun.py", "Admin API v2; solo oraculo-nodo-* con etiqueta propia")
    Component(gwfake, "Nube de ensayo", "adapters/infra/fake.py", "Se comporta como Cloud Run, en memoria")
  }

  System_Ext(cloudrun, "Cloud Run", "Nodos reales")

  System_Ext(vertex, "Vertex AI", "Gemini con grounding")

  Rel(raiz, http, "Construye")
  Rel(raiz, servicio, "Inyecta puertos y políticas")
  Rel(http, esquemas, "Valida la entrada")
  Rel(http, servicio, "Invoca casos de uso")
  Rel(servicio, limites, "Pide permiso antes de escribir")
  Rel(servicio, puertos, "Depende de")
  Rel(servicio, dominio, "Aplica reglas")
  Rel(memoria, puertos, "Implementa Repository")
  Rel(vertexad, puertos, "Implementa OracleGateway")
  Rel(mock, puertos, "Implementa OracleGateway")
  Rel(vertexad, ruta, "Payload")
  Rel(mock, ruta, "Payload")
  Rel(ruta, dominio, "AcceptancePolicy decide")
  Rel(vertexad, vertex, "generateContent", "HTTPS/JSON")
  Rel(http, nube, "Controles del ponente")
  Rel(servicio, nube, "Resuelve preguntas 'simulacion'")
  Rel(nube, sim, "Avanza y consulta")
  Rel(gentopo, puertos, "Implementa TopologyGenerator")
  Rel(gentopo, vertex, "generateContent", "HTTPS/JSON")
  Rel(http, infra, "Ciclo, fallas, apagado, vigilia")
  Rel(infra, nube, "Lee la topología adoptada")
  Rel(infra, actuacion, "Recorta el deseo y revisa cada acción")
  Rel(gwrun, puertos, "Implementa NodeGateway")
  Rel(gwfake, puertos, "Implementa NodeGateway")
  Rel(gwrun, cloudrun, "Crea, escala, repara, borra; sondea", "HTTPS")

  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```
<!-- /mmd -->

| Capa | Contiene | Puede importar |
| --- | --- | --- |
| `domain/` | Mercado, LMSR, políticas (`AcceptancePolicy`, `CensusPolicy`, `TopologyPolicy`, `ActuationPolicy`), simulación | solo `domain` |
| `application/` | Casos de uso, puertos, límites de abuso, controlador de infraestructura | `domain` |
| `adapters/` | Vertex AI, Cloud Run, repositorio en memoria, nube de ensayo | `domain`, `application` |
| `entrypoints/http/` | FastAPI, esquemas, controles de borde, pantallas | `domain`, `application` |
| `main.py`, `config.py` | Raíz de composición: lee el entorno, falla cerrado y conecta todo | todo |

## 4. Despliegue

Del commit a producción, con las compuertas de seguridad en orden.

<!-- mmd:c4-despliegue -->
```mermaid
C4Deployment
  title Despliegue — pipeline con compuertas de seguridad y límites de costo

  Deployment_Node(dev, "Laptop de la ponente", "git, VS Code y gcloud") {
    Container(repo, "Repositorio", "Python 3.12", "pre-commit: gitleaks, ruff con bandit, pip-audit, tests/security")
  }

  Deployment_Node(gcp, "Google Cloud", "oraculo-6d1578, us-east1") {
    Deployment_Node(cb, "Cloud Build") {
      Container(pipe, "cloudbuild.yaml", "compuertas en orden", "secretos → bandit → pip-audit → pruebas → imagen → Trivy → publicar → desplegar")
    }
    Deployment_Node(ar, "Artifact Registry") {
      Container(imagen, "Imagen OCI", "python:3.12-slim por digest", "Dependencias con hash; usuario sin shell; APP_MODULE en lista blanca")
    }
    Deployment_Node(run, "Cloud Run") {
      Container(api, "oraculo-api", "FastAPI", "Facturación por petición, min 0, max 1; sin /api/docs en producción")
      Container(nodo, "oraculo-nodo-*", "FastAPI mínima", "Privados; ¼ vCPU; solo si el ponente activa la actuación")
    }
    Deployment_Node(iam, "IAM y secretos") {
      Container(sarun, "oraculo-run", "identidad de la API", "aiplatform.user, run.developer, run.invoker; lectura del repo y del secreto")
      Container(sanodo, "oraculo-nodo", "identidad de los nodos", "Sin ningún rol")
      Container(savig, "oraculo-vigilia", "identidad de Scheduler", "Sin ningún rol; solo firma su token OIDC")
      Container(secreto, "Secret Manager", "oraculo-presenter-key", "Una región; acceso solo para oraculo-run")
    }
    Deployment_Node(costo, "Límites de costo") {
      Container(vigilia, "Cloud Scheduler", "oraculo-vigilia", "Cada 15 min")
      Container(budget, "Presupuesto", "10 USD/mes", "Alertas al 50, 90 y 100 %; no corta el gasto")
    }
  }

  Rel(repo, pipe, "gcloud builds submit")
  Rel(pipe, imagen, "push solo si Trivy pasa")
  Rel(imagen, api, "gcloud run deploy")
  Rel(api, nodo, "Crea y repara", "Admin API v2")
  Rel(api, sarun, "actúa como")
  Rel(nodo, sanodo, "actúa como")
  Rel(vigilia, savig, "firma como")
  Rel(vigilia, api, "POST /api/infra/vigilia", "OIDC")
  Rel(api, secreto, "lee al arrancar")

  UpdateLayoutConfig($c4ShapeInRow="2", $c4BoundaryInRow="1")
```
<!-- /mmd -->

## 5. Flujos clave

### Del modelo a Cloud Run: dos compuertas

```mermaid
sequenceDiagram
  autonumber
  actor P as Ponente
  participant API as oraculo-api
  participant G as Gemini (Vertex AI)
  participant TP as TopologyPolicy
  participant C as InfraController
  participant AP as ActuationPolicy
  participant CR as Cloud Run
  P->>API: Pedir al modelo (X-Presenter-Key)
  API->>G: contexto: regiones, costos, restricciones
  G-->>API: JSON con réplicas por región (no confiable)
  API->>TP: ¿forma, regiones, presupuesto, disponibilidad, latencia?
  alt rechazada
    TP-->>API: razones → se muestra la traza, nada cambia
  else aceptada y mejor que la actual
    TP-->>API: se adopta en la simulación
    P->>API: Activar actuación
    loop cada 10 s, solo mientras el ponente mira
      C->>CR: listar oraculo-nodo-* (estado real)
      C->>C: demanda real (Holt) → instancias mínimas
      C->>AP: recortar el deseo y revisar cada acción
      AP-->>C: permitidas y bloqueadas, con razón
      C->>CR: crear / escalar / borrar (solo lo permitido)
    end
  end
```

### Falla real y autorreparación

```mermaid
sequenceDiagram
  autonumber
  actor P as Ponente
  participant C as InfraController
  participant D as Detector EWMA
  participant CR as Cloud Run
  participant N as oraculo-nodo-us-east1
  P->>C: caída en us-east1
  C->>CR: revisión nueva con NODO_FALLA=caida
  loop cada ciclo
    C->>N: GET /salud (token de identidad)
    N-->>C: 503
    C->>D: latencia 3000 ms
  end
  D-->>C: anomalía dos veces seguidas (z ≫ 4)
  C->>CR: revisión nueva sana (reparar)
  C->>N: GET /salud
  N-->>C: 200 en ~40 ms → incidente cerrado
  Note over C: Medido en producción: detectada a los 31 s, reparada a los 53 s
```

## 6. Fronteras de confianza

| Frontera | Qué cruza | Control | Dónde |
| --- | --- | --- | --- |
| Internet → API | Peticiones de la audiencia | Token por nombre (hash SHA-256 guardado), límites de ritmo, esquemas con patrones | `api.py`, `service.py`, `limits.py`, `schemas.py` |
| Internet → API | Acciones del ponente | `X-Presenter-Key` comparada en tiempo constante; ≥ 32 caracteres o no arranca | `api.py`, `config.py` |
| Cloud Scheduler → API | Vigilia | Token OIDC firmado por Google: firma, audiencia y cuenta | `google_auth.py`, `api.py` |
| Navegador | HTML y JS propios | CSP `script-src 'self'`, sin scripts en línea, sin `eval` | `api.py`, `static/` |
| API → Gemini | Respuestas del modelo | Dato no confiable: `AcceptancePolicy` y `TopologyPolicy` | `domain/` |
| API → Cloud Run | Acciones sobre la cuenta | `ActuationPolicy`; solo `oraculo-nodo-*` con etiqueta propia; identidad con permisos mínimos | `domain/cloud/infra.py`, `adapters/infra/cloudrun.py` |
| Código → imagen | Dependencias y sistema base | Lock con hashes, base por digest, Trivy, pip-audit | `requirements.lock`, `Dockerfile`, `cloudbuild.yaml` |

## 7. Regenerar los diagramas

```bash
make diagramas   # copia los .mmd aquí y renderiza el de contexto a PNG y SVG
```

El render usa `mermaid-cli` con el Chrome instalado (`CHROME=...` para otra
ruta). El diagrama de contexto está escrito como `flowchart` con la convención
de colores de C4, porque el layout C4 nativo de Mermaid amontona las etiquetas.
