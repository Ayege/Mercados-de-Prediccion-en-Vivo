# Tipos de pregunta

Qué mide el precio según el tipo de pregunta, cómo elegir qué preguntas se
siembran al arrancar y qué fallos del oráculo se pueden provocar para ver cómo
los rechaza el código.

## Qué mide cada tipo

Cada mercado declara su tipo, porque el tipo cambia lo que mide el precio:

| Tipo | Ejemplo | Qué mide el precio | Quién lo resuelve |
| --- | --- | --- | --- |
| `presente` | ¿Salió Python 3.15.0 antes del 8/10/2026? | La respuesta ya existe, pero nadie en la sala la sabe con certeza. El precio agrega conocimiento disperso **sobre el presente** | El oráculo, con evidencia |
| `futuro` | ¿Cerrará el USD/DOP sobre 65 el 31/12/2026? | Hoy no se puede resolver, a propósito: lo correcto es que el oráculo diga **SIN RESOLVER** | El oráculo, que debe negarse |
| `sala` | ¿Más de la mitad de esta sala desplegó un viernes este mes? | Cada persona conoce una parte y ningún buscador la tiene. Aquí el mecanismo de agregación se luce | Un censo privado de la sala |
| `simulacion` | ¿La primera caída de nodo se reparará en menos de 6 ticks? | Comportamiento emergente de los agentes, con plazo de minutos | El código de la simulación |
| `simulacion` con predicado real | ¿La primera falla en un nodo real de Cloud Run se reparará en menos de 2 minutos? | Lo mismo, sobre infraestructura real | Lo medido en Cloud Run |

Dos variantes de las preguntas `presente` y `futuro`, explicadas en
[NOTICIAS.md](NOTICIAS.md):

- **Con encuadre:** dos titulares sobre el mismo hecho; cada persona ve uno.
- **Desde las noticias:** la pregunta nace de las noticias del día y cuatro
  agentes apuestan según su dieta de medios.

Todos los mercados abren en 50 %, sin órdenes de la casa: cualquier movimiento lo
hizo la sala, o los agentes de noticias, cuyas órdenes se muestran una por una.

### El censo

Las preguntas `sala` se resuelven con un censo privado. Sus límites:

- Es autodeclarado y quien responde también apuesta: alguien puede mentir para
  ganar. La mitigación es débil: una respuesta por persona, inmutable, y solo se
  publica el conteo.
- Con menos de 5 respuestas se niega a resolver (`CENSUS_MIN_RESPONSES`). Es la
  misma idea que el mínimo de fuentes del oráculo.

## Juegos de preguntas

Las preguntas que se siembran al arrancar se eligen con `SEED_SET`. Los juegos se
combinan con `+`, por ejemplo `encuadre+nube_real`. Las preguntas desde las
noticias no se siembran: se crean en vivo desde la proyección.

| `SEED_SET` | Preguntas |
| --- | --- |
| `ninguna` | Ninguna: la sala empieza vacía y las preguntas se crean desde las noticias |
| `real` | Kubernetes, Python, iPhone 18, USD/DOP, una pregunta `sala`, la autorreparación de un nodo real y la cooperación del mercado real (4 agentes). Junto con `ninguna`, el único que acepta producción. **El que usa producción** |
| `oraculo` (default) | Kubernetes, Python, iPhone 18 (`presente`, con la fecha límite ya pasada) y USD/DOP (`futuro`) |
| `agregacion` | Tres preguntas `sala` sobre la práctica de quienes participan |
| `mixta` | Python, USD/DOP y una pregunta `sala` |
| `encuadre` | Python y Kubernetes con dos titulares cada una, más una `sala` de control |
| `nube` | Cooperación, autorreparación, topología y credulidad (simuladas) |
| `nube_real` | Cooperación, topología y credulidad (simuladas), más la autorreparación de un nodo real y la cooperación del mercado real. Necesita `INFRA_MODE=real` |

**En producción todo es real.** La API no siembra ni deja crear preguntas que
resuelva el laboratorio simulado, ni titulares sin el enlace `https` donde los
publicó el medio. Por eso `encuadre`, `nube` y `nube_real` solo sirven en local;
en producción, las preguntas con encuadre se crean con titulares reales (ver
[NOTICIAS.md](NOTICIAS.md#crear-una-pregunta-con-encuadre)). Para cambiarlo en
producción, ver [Cambiar las preguntas](DESPLIEGUE.md#cambiar-las-preguntas).

## Fallos del oráculo

La proyección tiene un selector de fallos («Modo demo») junto a «Preguntar a la IA». Sirven
para ver al código rechazar un veredicto:

| Fallo | Qué simula | Qué lo rechaza |
| --- | --- | --- |
| `baja_confianza` | El modelo responde con confianza 0.55 | `AcceptancePolicy`: confianza menor que `ORACLE_MIN_CONFIDENCE` |
| `un_dominio` | El grounding trae fuentes de un solo dominio | `AcceptancePolicy`: menos dominios que `ORACLE_MIN_SOURCES` |
| `json_malformado` | El modelo responde en prosa | `interpret`: fail-closed al no poder leerla |
| `red_caida` | Falla la llamada a Vertex AI | `run`: fail-closed ante cualquier excepción |
| `noticia_como_verdad` | Solo con encuadre: el sistema le pasa el titular al modelo como hecho verificado | `FramingPolicy`: el veredicto cambia con el titular |

Los cuatro primeros se inyectan en la respuesta cruda del modelo, antes del mismo
código que lee a Vertex AI: lo que se ve rechazar es la ruta de producción, no una
simulación aparte. Cada consulta queda registrada con su fallo, el precio de la
sala en ese momento y el motivo del rechazo.
