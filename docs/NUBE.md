# La nube autónoma

`/nube.html` muestra una nube que intenta gobernarse sola. La visión completa
(infraestructura que se gobierna, se optimiza y se repara sola en un mercado
descentralizado) es mucho más grande de lo que cabe en una demo, y casi todo
en ella es todavía investigación. Cada pieza está aquí en su versión más pequeña
que todavía es honesta, y la interfaz dice cuál es.

## Qué es real y qué es laboratorio

| La visión pide | Real (con `INFRA_MODE=real`) | Laboratorio simulado | Lo que **no** es |
| --- | --- | --- | --- |
| Predecir la demanda y ajustar la oferta | Holt predice las peticiones por segundo de la sala y fija las instancias mínimas de los nodos | Holt-Winters con autoescalado por agente | No es un modelo profundo; la demanda son los móviles de la sala |
| Descubrir estrategias de precios | Q-learning sobre la ganancia real de cada agente: lo cobrado a tiempo menos el costo real de Cloud Run | Lo mismo con doce agentes | No es RL profundo: pocos estados y 3 acciones |
| Formar coaliciones | Contratos que exigen dos regiones, ejecutados de verdad, pagados solo si cumplen y repartidos por valor de Shapley exacto | Lo mismo con cpu simulada | La formación es codiciosa, no un equilibrio negociado |
| Evolucionar | El gen `warm` cambia la instancia mínima real; la aptitud es la ganancia real | Algoritmo genético (margen, reserva, cooperación, previsión, credulidad) contra la dinámica del replicador | No se reescriben a sí mismos: evolucionan unos pocos parámetros |
| Detectar y reparar fallas | Sondeos con token de identidad, detector EWMA y una revisión sana como reparación | Lo mismo sobre nodos ficticios | La falla real se inyecta (`NODO_FALLA`), no es espontánea |
| Generar arquitecturas | La topología adoptada se despliega como `oraculo-nodo-<región>` tras pasar `ActuationPolicy` | Gemini y un algoritmo genético proponen; `TopologyPolicy` decide | El modelo nunca llama a la nube |
| Mercado de recursos | Subasta de precio uniforme de la demanda real entre 4 agentes, con tope de 12 peticiones por ciclo | Subasta por recurso entre doce agentes | **No es descentralizado**: hay un subastador central, y el dinero es contable |
| Reaccionar a noticias | — | Gen `credulidad` y noticias alarmistas (ver [NOTICIAS.md](NOTICIAS.md#4-credulidad-en-el-laboratorio-simulado)) | Un parámetro, no un modelo de opinión |

**Por qué existe el laboratorio:**

- **Va a cámara rápida.** Una generación real dura unos 2 minutos (12 ciclos de
  10 s); una simulada, 24 s.
- **Se controla.** Sus fallas y su demanda las decide el ponente.
- **Se puede ensayar.** Es determinista dada la semilla (`SIM_SEED`).

## La sala no decide la topología

Las preguntas sobre la nube son **apuestas sobre lo que va a pasar**, no
palancas. La topología cambia así:

1. El ponente pulsa «Pedir al modelo» o «Búsqueda evolutiva».
2. **`TopologyPolicy` revisa si el diseño es bueno:** presupuesto, regiones,
   disponibilidad, latencia y forma. Si pasa y mejora la actual, se adopta.
3. **`ActuationPolicy` revisa si se puede ejecutar en esta cuenta:**
   - solo regiones permitidas;
   - 3 servicios como máximo;
   - 2 instancias mínimas en total y 2 máximas por región;
   - un cambio de escala por minuto por región y 3 llamadas por ciclo;
   - solo servicios `oraculo-nodo-*` con la etiqueta `oraculo-demo=true`.
4. Solo entonces, con la actuación activa, se llama a Cloud Run.

Lo que sí hace la sala es **generar la demanda**: cada consulta de los móviles
es tráfico real que Holt predice y que los agentes se disputan.

La actuación arranca **en pausa**. `INFRA_MODE` puede ser:

| Modo | Qué hace |
| --- | --- |
| `apagado` (default) | No hay infraestructura real |
| `ensayo` | Nube falsa en memoria que se comporta como Cloud Run |
| `plan` | Cloud Run valida cada acción con `validateOnly`, sin aplicarla |
| `real` | Actúa sobre Cloud Run de verdad |

## El mercado real, con números

Los precios vienen de la API pública de Cloud Billing: precios de lista, sin
descontar el nivel gratuito. El 2026-10-05, en us-east1:

| Concepto | Costo |
| --- | --- |
| Una petición de trabajo (¼ vCPU, 256 MiB, redondeada a 100 ms) | 1,06 µUSD |
| Una hora con instancia mínima encendida | 0,45 centavos (0,63 en regiones de nivel 2) |
| Una hora de mercado con 12 peticiones cada 10 s y un agente caliente | ≈ 1 centavo |

Medido en producción el 2026-10-05: 5 minutos, 24 ciclos, 4 agentes.

| Agente | Región | Latencia real (p50) | Resultado |
| --- | --- | --- | --- |
| r1 | us-east1 | 14 ms | Gana: la misma región que la API |
| r2 | us-central1 | 55 ms | Gana menos |
| r3 | europe-west1 | 111 ms | Gana; mejor de la generación 2 |
| r4 | southamerica-east1 | 138 ms | Pagó instancia caliente en una región de nivel 2 y casi no vendió: −157 µUSD. En la generación 2, la evolución le apagó la instancia |

- **Contratos:** los tres de dos regiones se cumplieron, 6 de 6 a tiempo.
- **Peticiones:** 468, todas con 200.
- **Costo total:** 531 µUSD, es decir, 0,05 centavos.

Con el tráfico de una sala, mantener una instancia caliente cuesta más de lo que
se gana evitando arranques en frío, y la evolución suele descubrirlo. No está
programado: es la economía real de Cloud Run.

## Lo que el laboratorio enseña sin que nadie lo programe

- **El margen se va a cero.** El Q-learning empuja los precios hacia el costo:
  competencia de Bertrand. Solo suben con escasez.
- **La cooperación no siempre sobrevive.** Con unas semillas los cooperativos
  dominan; con otras se extinguen en dos generaciones.
- **Predecir bien es difícil de demostrar.** Sin perturbaciones, Holt-Winters
  apenas le gana al pronóstico ingenuo. Con picos, la diferencia crece.
- **Creer noticias no siempre se castiga.** Con noticias que aciertan el 30 %,
  la credulidad sube o baja según la semilla.
