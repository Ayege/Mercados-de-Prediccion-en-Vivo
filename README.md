# Oráculo

Un mercado de predicción en vivo. Las personas de una sala apuestan desde el
móvil y los precios son probabilidades. Un modelo de IA intenta resolver cada
pregunta, y el código decide si acepta lo que dice. Todo corre en Google Cloud.

**Demo:** https://oraculo-api-346171942822.us-east1.run.app

La idea que atraviesa todo el proyecto es una sola: **el modelo propone, el
código dispone.** Un LLM es un componente no confiable, y lo interesante es ver
dónde y por qué el código le dice que no.

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
| `/proyeccion.html` | Todos, en una pantalla compartida | Ver los mercados y el código de sala; quien modera consulta al oráculo y crea preguntas desde las noticias |
| `/nube.html` | Quien modera | Ver y controlar la nube |

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
