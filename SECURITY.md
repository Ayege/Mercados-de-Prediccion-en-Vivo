# Seguridad

Este documento dice qué protege Oráculo, de quién, con qué controles y qué
riesgos quedan abiertos a sabiendas. La arquitectura y las fronteras de
confianza están en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).

## Reportar un problema

No abras un issue público. Escribe a la responsable del repositorio con los
pasos para reproducirlo. Si el problema afecta a la demo desplegada, el
interruptor inmediato es **Apagar todo** en `/nube.html`, o borrar los
servicios `oraculo-nodo-*` (ver [Al terminar una sesión](docs/DESPLIEGUE.md#al-terminar-una-sesión)).

## Qué se protege

| Activo | Por qué importa |
| --- | --- |
| La cuenta de Google Cloud y su factura | El controlador crea servicios reales. Un abuso cuesta dinero |
| La clave de moderación | Quien la tiene crea mercados, resuelve, activa la actuación e inyecta fallas |
| El pipeline de publicación | Lo que corre en Cloud Build puede publicar imágenes y desplegar la API |
| La integridad del mercado y del censo | Si alguien apuesta o vota por otros, la demo pierde sentido |
| La imagen y sus dependencias | Una dependencia alterada corre con la identidad de la API |
| La reputación de quien proyecta | Una pantalla compartida con contenido inyectado es un incidente público |

## Modelo de amenazas (STRIDE)

| Amenaza | Escenario | Control | Prueba que lo fija |
| --- | --- | --- | --- |
| **S**uplantación | Alguien apuesta o responde el censo con el nombre de otra persona | Al entrar, el servidor entrega un token aleatorio (`secrets.token_urlsafe`) y guarda solo su SHA-256; cada escritura exige `X-User-Token` | `test_nobody_can_trade_with_someone_elses_name` |
| **S**uplantación | Alguien se hace pasar por Cloud Scheduler para llamar a la vigilia | Token OIDC firmado por Google; se verifican firma, expiración, audiencia y cuenta `oraculo-vigilia` | `test_scheduler_can_only_call_the_vigil_with_a_valid_oidc_token` |
| **S**uplantación | Alguien de fuera de la sala crea cuentas, llena la sala o agota el límite de entradas | Entrar exige el código de sala, que solo muestra la proyección de quien modera (se genera al arrancar; producción no arranca sin él) | `test_entering_needs_the_room_code_shown_on_the_projector`, `test_production_refuses_to_start_without_a_room_code` |
| **T**ampering | Una ruta de escritura nueva queda sin autenticación | Toda ruta `POST`, `PUT`, `PATCH` o `DELETE` exige la clave de moderación salvo una lista blanca de tres rutas de la audiencia; las lecturas reservadas (`/api/sala`, `/api/noticias`) también | `test_every_write_route_requires_the_presenter_unless_it_is_an_audience_write`, `test_presenter_reads_require_the_presenter` |
| **T**ampering | Gemini propone algo inválido o inyectado desde una página web | El modelo es un componente no confiable: `AcceptancePolicy` y `TopologyPolicy` deciden, fail-closed | `tests/domain/test_policy.py`, `test_infra_policy.py` |
| **S**uplantación | Alguien opera o consulta como un agente de noticias | Los agentes se llaman `agente:<dieta>`; la audiencia no puede usar «:» en su nombre, y la credencial vacía de un agente nunca coincide con un hash | `test_nobody_can_take_an_agents_name`, `test_agents_cannot_be_used_from_outside` |
| **T**ampering | Se le atribuye a un medio un titular que no publicó | El titular nunca sale del texto del modelo: viene de Google News, que lo atribuye al medio con `<source url>`. El modelo solo elige titulares por su número. En ensayo, solo medios ficticios `.example` | `test_outlet_comes_from_the_index_attribution_and_suffix_is_stripped`, `test_editor_can_only_pick_headlines_by_number`, `test_mock_desk_never_puts_words_in_real_outlets_mouths` |
| **T**ampering | El servidor descarga una URL arbitraria (SSRF) | El servidor solo descarga `news.google.com/rss/search`, sin seguir redirecciones, con 8 s y 1 MB como máximo; los enlaces que no son de Google News se descartan. El XML se lee sin parser de entidades | `test_links_outside_the_index_are_dropped`, `test_a_failing_side_is_empty_and_says_why` |
| **T**ampering | Un titular trae instrucciones para el modelo | Todo texto de terceros se escapa antes de ir entre etiquetas del prompt (un «</titular>» no cierra la etiqueta); llega como dato, nunca como instrucción de sistema; `FramingPolicy` rechaza un veredicto que cambia con el titular | `test_headlines_cannot_break_out_of_their_prompt_tags`, `test_vertex_puts_untrusted_news_in_the_user_turn` |
| **T**ampering | El controlador toca un servicio que no es suyo | Solo nombres `oraculo-nodo-*` y `oraculo-agente-r<n>`, solo regiones del catálogo, solo servicios con la etiqueta `oraculo-demo=true` y el rol correcto; validaciones con excepciones, no `assert` | `tests/adapters/test_cloudrun.py` |
| **T**ampering | Precios manipulados o incompletos alteran las decisiones del mercado | Los precios vienen del catálogo oficial de Cloud Billing por HTTPS con identidad de Google; si falta un precio, el mercado no opera (fail-closed) | `test_incomplete_catalog_fails_closed` |
| **T**ampering | Dependencia o imagen base alterada | `requirements.lock` y `requirements-dev.lock` con hashes e instalación `--require-hashes`; imagen base y todas las imágenes del pipeline fijadas por digest; `APP_MODULE` en lista blanca | `pip-audit --require-hashes` de ambos locks en pre-commit y pipeline |
| **E**levación de privilegios | Una herramienta del pipeline comprometida toma el proyecto | El build corre como `oraculo-build`: solo escribe en el repositorio de imágenes, despliega `oraculo-api` como `oraculo-run` y escribe logs. La cuenta de Compute por defecto ya no tiene `roles/editor` | `serviceAccount` en `cloudbuild.yaml`; IAM verificado en producción |
| **R**epudio | No saber quién activó la actuación, resolvió un mercado o abrió una pregunta | Cada escritura con clave de moderación o token de Cloud Scheduler, incluidos los intentos fallidos, deja una línea JSON de auditoría (`"auditoria": true`) en Cloud Logging, sin la clave. Cada decisión de `ActuationPolicy` queda con su razón | `test_presenter_actions_leave_an_audit_line` |
| **I**nformation disclosure | La vista pública revela el proyecto, las cuentas y los permisos | `GET /api/infra` sin clave oculta los mensajes de error internos | `test_public_view_hides_internal_errors` |
| **I**nformation disclosure | Saldos y posiciones de otras personas | `GET /api/users/{name}` exige el token de esa persona | `test_balances_are_private` |
| **I**nformation disclosure | Reconocimiento de la API | `/api/docs` y `/openapi.json` cerrados en producción | `test_api_docs_are_closed_in_production` |
| **I**nformation disclosure | La clave de ponente en variables o en el job | Secret Manager, con `secretAccessor` solo para `oraculo-run`; el job usa OIDC; la clave viaja en el fragmento `#` de la URL, que el navegador no envía | Verificado en producción |
| **D**enegación de servicio (económica) | Alguien consulta `/api/infra` sin parar para que la vigilia nunca apague los nodos | Solo el ponente cuenta como «alguien mira» y mueve el ciclo; los topes de `ActuationPolicy` limitan el gasto máximo | `test_public_infra_view_neither_keeps_nodes_alive_nor_runs_the_controller` |
| **D**enegación de servicio (económica) | Mucho tráfico hace que el mercado real envíe mucho trabajo pagado | `MarketBudget`: 12 peticiones de trabajo por ciclo sin importar la demanda, 1 agente caliente como máximo, 4 agentes; el ciclo solo corre mientras el ponente mira | `test_auction_never_sells_more_than_the_cost_cap`, `test_warm_budget_holds_in_real_services` |
| **D**enegación de servicio (económica) | Muchas búsquedas de noticias o consultas de agentes | Solo el ponente; una búsqueda cada 30 s; los agentes opinan una vez por pregunta (4 llamadas) | `test_searches_are_rate_limited`, `test_agents_opine_once_per_question` |
| **D**enegación de servicio (económica) | Inundar la API para inflar la «demanda real» y el autoescalado | Solo cuenta como demanda una petición de la audiencia con token que obtuvo respuesta; `ActuationPolicy` acota igual el gasto | `test_anonymous_traffic_is_not_counted_as_demand` |
| **D**enegación de servicio | Muchas órdenes hacen crecer sin límite la serie de precios que se envía a cada móvil | La serie se queda en 400 puntos: al pasarse, conserva uno de cada dos | `test_price_history_stays_bounded_and_keeps_both_ends` |
| **D**enegación de servicio | Agotar la memoria de la única instancia o saturar las órdenes | Tope de 2000 cuentas, 120 entradas por minuto, 10 órdenes por persona cada 10 s, esquemas con longitudes máximas | `test_orders_are_rate_limited_per_person` |
| **E**levación de privilegios | XSS en las pantallas proyectadas | Escape de todo dato en `innerHTML`; `textContent` para datos externos; CSP `script-src 'self'`; sin scripts ni manejadores en línea; sin `eval` | `test_pages_have_no_inline_scripts_or_handlers`, `test_scripts_do_not_use_dynamic_code`, `test_security_headers_everywhere` |
| **E**levación de privilegios | Un nodo comprometido ataca la cuenta | Los nodos corren como `oraculo-nodo`, sin ningún rol | IAM |
| **E**levación de privilegios | Producción arranca abierta por olvido | En Cloud Run (`K_SERVICE`) o con `INFRA_MODE=plan|real`, sin una clave de ≥ 32 caracteres la app no arranca | `test_production_refuses_to_start_without_a_strong_key` |

## Seguridad desplazada a la izquierda

Cada control se automatiza lo más temprano posible. Los mismos chequeos corren
en tres momentos, y cada uno es una compuerta:

| Momento | Herramienta | Qué detiene |
| --- | --- | --- |
| Al escribir | Reglas `S` de ruff (bandit) en el editor | `assert` como control, azar no criptográfico, subprocess inseguro |
| Antes de cada commit | `pre-commit` ([.pre-commit-config.yaml](.pre-commit-config.yaml)) | Secretos (gitleaks), llaves privadas, archivos grandes, ruff con bandit, `tests/security`, `pip-audit` |
| En cada build | [cloudbuild.yaml](cloudbuild.yaml) | Secretos → ruff con bandit → `pip-audit` → toda la suite → imagen → **Trivy** (ALTAS y CRÍTICAS con arreglo) → recién entonces publicar y desplegar |
| En producción | Cabeceras, CSP, OIDC, límites, vigilia, presupuesto | Lo que se haya escapado |

La primera ejecución del pipeline endurecido funcionó como debía: **Trivy
bloqueó la imagen** por CVE-2026-103111 (`libpcre2-8-0`, alta, con arreglo en
Debian). El `Dockerfile` ahora aplica las actualizaciones de seguridad del
sistema al construir, y la segunda ejecución pasó con 0 vulnerabilidades altas
o críticas.

Para correrlo todo a mano: `make seguridad`.

## Riesgos aceptados

Estos riesgos están abiertos a sabiendas, porque cerrarlos cuesta más de lo
que protegen en una demo de 40 minutos:

- **Identidades múltiples (sybil) dentro de la sala.** Quien tiene el código de
  sala puede entrar con muchos nombres. Los topes limitan el daño, pero el
  censo sigue siendo autodeclarado y manipulable, y así se presenta.
- **Fuerza bruta del código de sala.** Son 6 caracteres de un alfabeto de 32
  (unos mil millones de combinaciones) y no hay límite de intentos fallidos:
  un límite global permitiría a un atacante bloquear la entrada a todos. Con
  una sola instancia, adivinarlo lleva días; una sesión dura una hora y el
  código cambia con cada revisión. Los intentos quedan en los logs de Cloud Run.
- **`run.developer` con condición.** `oraculo-run` solo puede crear y modificar
  servicios `oraculo-nodo-*` y `oraculo-agente-*`: modificar `oraculo-api` o
  crear otro servicio da 403 (verificado con validateOnly). Pero Cloud Run no
  informa el nombre del servicio al revisar lecturas y borrados, así que una API
  comprometida todavía podría **borrar** `oraculo-api`. Es disponibilidad, no
  escalada: no puede redesplegarla con otro código. La mitigación completa es
  desplegar los nodos en un proyecto aparte.
- **La clave de moderación en el navegador.** Vive en el fragmento de la URL y
  en el historial del navegador de quien proyecta. Cámbiala al terminar cada
  sesión: `gcloud secrets versions add oraculo-presenter-key --data-file=-`.
- **Estilos en línea.** La CSP permite `style-src 'unsafe-inline'` porque los
  gráficos SVG lo usan. Inyectar estilo es mucho menos grave que inyectar
  script, que sí está prohibido.
- **Arranque en frío con una sola instancia.** Con `min-instances 0` y `max 1`,
  una ráfaga al arrancar recibe 429 de Cloud Run. Es disponibilidad, no
  integridad; durante una sesión se sube a `min-instances 1`.
- **El presupuesto no corta el gasto.** Solo alerta. Los frenos reales son
  `ActuationPolicy`, la escala a cero y la vigilia.
- **La foto del estado se lee con pickle.** pickle ejecuta código al leer, así
  que antes se verifica la firma HMAC (clave derivada de `PRESENTER_KEY`), la
  huella del código y la edad. Quien pueda escribir en el bucket sin conocer la
  clave no puede colar una foto. El bucket no es público y solo `oraculo-run`
  escribe en él.
- **Sin WAF ni Cloud Armor.** La API está detrás del frontend de Google. Para
  más que una sala, el siguiente paso sería un balanceador con Cloud Armor.

## Mantenimiento

- Cambia la clave de moderación al terminar cada sesión.
- Corre `make lock` y `pre-commit autoupdate` una vez al mes y revisa el diff.
- Actualiza los digests de las imágenes del pipeline con la misma frecuencia
  (ver «Publicar cambios» en [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md)).
- Para actualizar la imagen base, consulta el digest nuevo de
  `python:3.12-slim` y cámbialo en el `Dockerfile`, en un commit propio.
- Revisa los avisos del presupuesto: un gasto inesperado es una señal de
  seguridad, no solo de costo.
