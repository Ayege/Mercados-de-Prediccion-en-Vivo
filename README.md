# Oráculo

Un mercado de predicción en vivo para dar una charla. La audiencia apuesta desde
el móvil y los precios son probabilidades. Un modelo de IA intenta resolver cada
pregunta, y el código decide si acepta lo que dice. Todo corre en Google Cloud.

**Demo:** https://oraculo-api-346171942822.us-east1.run.app

La idea que atraviesa todo el proyecto es una sola: **el modelo propone, el
código dispone.** Un LLM es un componente no confiable, y lo interesante es ver
dónde y por qué el código le dice que no.

## Qué se puede mostrar

La demo tiene tres partes. Se pueden dar por separado o juntas.

| Parte | Qué pasa en el escenario | Cómo funciona |
| --- | --- | --- |
| **Creencia contra evidencia** | La sala apuesta sobre preguntas que nadie sabe con certeza. Gemini busca evidencia en la web, y una política en código acepta o rechaza su veredicto. Se pueden provocar rechazos en vivo | [Guía de la charla](docs/CHARLA.md) |
| **Noticias y opinión** | La sala se divide al azar y cada mitad lee un titular distinto sobre el mismo hecho. Las preguntas también pueden nacer de las noticias del día, con cuatro agentes que solo leen medios de izquierda, solo de derecha, ambos o ninguno, y apuestan en el mismo mercado | [Noticias, encuadre y opinión](docs/NOTICIAS.md) |
| **Nube autónoma** | Bucles que actúan sobre Cloud Run de verdad: despliegan la topología que propone un modelo, escalan con el tráfico de los móviles, reparan fallas reales y tienen un mercado de agentes con precios reales. Un laboratorio simulado muestra lo mismo a cámara rápida | [La nube autónoma](docs/NUBE.md) |

Hay tres pantallas:

| Pantalla | Quién la ve | Para qué |
| --- | --- | --- |
| `/` | La audiencia, en el móvil | Apostar y responder el censo |
| `/proyeccion.html` | Todos, en el proyector | Ver los mercados, consultar al oráculo y crear preguntas desde las noticias |
| `/nube.html` | El ponente, en el proyector | Ver y controlar la nube |

Los controles del ponente aparecen solo si la URL termina en `#clave=…`.

## Probarlo en cinco minutos

Requiere Python 3.12 o superior. Sin credenciales de Google Cloud, todo corre en
modo de ensayo: oráculo simulado, medios ficticios y nada que cobre.

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

Abre la audiencia en http://localhost:8080, la proyección en
http://localhost:8080/proyeccion.html y la nube en
http://localhost:8080/nube.html. Para elegir otras preguntas, pon por ejemplo
`SEED_SET=encuadre+nube` en `.env` (ver
[los juegos de preguntas](docs/CHARLA.md#elegir-las-preguntas)). Más formas de
ensayar, incluida la infraestructura simulada, en
[CODIGO.md](docs/CODIGO.md#ensayar-sin-tocar-la-nube).

## Documentación

| Documento | Para quién | Qué tiene |
| --- | --- | --- |
| [Guía de la charla](docs/CHARLA.md) | Quien presenta | Pantallas, tipos de pregunta, juegos de preguntas, fallos para provocar, guiones de 40 minutos, qué afirmar desde el escenario y la lista de antes y después |
| [Noticias, encuadre y opinión](docs/NOTICIAS.md) | Quien presenta o quiere entender esa parte | El experimento de los dos titulares, la prueba del oráculo, los agentes con dieta de medios y la lista de medios con sus fuentes |
| [La nube autónoma](docs/NUBE.md) | Quien presenta o quiere entender esa parte | Qué es real y qué es laboratorio, las dos compuertas, el mercado real con números medidos |
| [El código](docs/CODIGO.md) | Quien cambia el código | Capas, estructura, tests, cómo ensayar y las decisiones de diseño |
| [Arquitectura](docs/ARQUITECTURA.md) | Quien cambia el código | Diagramas C4, secuencias y fronteras de confianza |
| [Despliegue](docs/DESPLIEGUE.md) | Quien opera Google Cloud | Costos, permisos, primer despliegue, publicar cambios, cambiar de charla y limpieza |
| [Seguridad](SECURITY.md) | Todos | Modelo de amenazas, cada control con el test que lo fija y los riesgos aceptados |

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
- **Seguridad en cada paso.** Clave de ponente en Secret Manager, CSP estricta,
  identidades con permisos mínimos, y un pipeline que corre gitleaks, bandit,
  pip-audit, la suite completa y Trivy antes de publicar.

![Diagrama de contexto](docs/c4-nivel1-contexto.png)

## Pendiente

- Conectar el trigger de Cloud Build al repositorio de GitHub.
- Persistir el estado si tuviera que sobrevivir a que la API escale a cero.
- Una pregunta de cooperación resuelta por el mercado real (4 agentes), además
  de la simulada.
- Medios dominicanos en la lista, cuando haya una clasificación publicada que se
  pueda citar.
