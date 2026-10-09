// Utilidades compartidas por la vista de la audiencia y la de proyección.

// Textos para quien no conoce el proyecto: qué es la pregunta y quién la decide, sin jerga.
const TIPOS = {
  presente: {
    etiqueta: "Ya pasó",
    mide: "La respuesta ya existe. ¿La sala la sabe sin buscarla? Al final, la IA la busca en internet.",
  },
  futuro: {
    etiqueta: "Todavía no se sabe",
    mide: "Hoy nadie puede saberlo. Si la IA es honesta, dirá «todavía no se sabe».",
  },
  sala: {
    etiqueta: "Sobre ustedes",
    mide: "Solo ustedes tienen la respuesta. Se decide con una encuesta privada, no con la IA.",
  },
  simulacion: {
    etiqueta: "Nube simulada",
    mide: "La decide una simulación: nadie sabe de antemano qué harán sus agentes.",
  },
  noticias: {
    etiqueta: "De las noticias",
    mide: "Sale de los titulares de hoy. Cuatro bots leen medios distintos y también apuestan. La IA la decide cuando llegue la fecha.",
  },
  real: {
    etiqueta: "Nube real",
    mide: "La decide lo que pase de verdad en Google Cloud, medido con cronómetro.",
  },
};

// El tipo que se muestra: las preguntas que resuelve la infraestructura real tienen el suyo.
function tipo(m) {
  if (m.topic) return TIPOS.noticias;
  return TIPOS[m.resolver === "infraestructura real" ? "real" : m.kind];
}

// Las preguntas que nacieron de las noticias van primero, la más reciente arriba.
function ordenar(mercados) {
  const noticias = mercados.filter(m => m.topic).reverse();
  return [...noticias, ...mercados.filter(m => !m.topic)];
}

const RESULTADO = { YES: "SÍ", NO: "NO", UNRESOLVED: "AÚN NO SE SABE" };

// Barra partida SÍ/NO: lo que cree la sala, legible de un vistazo y desde lejos.
function barra(p) {
  const si = Math.round(p * 100);
  return `<div class="barra" role="img" aria-label="La sala cree ${si} % SÍ y ${100 - si} % NO">
    <span class="barra-si" style="width:${si}%">${si >= 12 ? `SÍ ${si} %` : ""}</span>
    <span class="barra-no" style="width:${100 - si}%">${100 - si >= 12 ? `NO ${100 - si} %` : ""}</span>
  </div>`;
}

// Por qué no hubo respuesta, en palabras. Las líneas «política: …» las escribe AcceptancePolicy;
// el censo y la nube ya explican su motivo en `reasoning`.
function motivo(m) {
  const v = m.oracle;
  if (m.resolver === "censo") return `Hacen falta más respuestas a la encuesta privada (${m.census_count} hasta ahora).`;
  if (m.resolver !== "oráculo" && m.resolver) return esc(v.reasoning);
  const politica = v.trace.find(t => t.startsWith("política:") && t.includes("→ UNRESOLVED")) || "";
  const fuentes = [...new Set(v.evidence.map(e => e.domain))];
  if (politica.includes("dominio")) {
    return `La IA creía saberlo, pero solo encontró ${fuentes.length || "una"} fuente` +
      `${fuentes.length ? ` (${esc(fuentes.join(", "))})` : ""} y pedimos al menos dos distintas.`;
  }
  if (politica.includes("confianza")) return "La IA no estaba lo bastante segura, así que no lo damos por cerrado.";
  if (v.trace.some(t => t.includes("fail-closed"))) return "No pudimos leer la respuesta de la IA. Ante la duda, no decidimos.";
  if (v.trace.some(t => t.startsWith("política de encuadre") && t.includes("→ UNRESOLVED"))) return "La IA cambió de opinión según el titular que leyó, así que no le creemos.";
  return "La IA no encontró pruebas suficientes: puede que todavía no haya pasado.";
}

const FALLOS = {
  baja_confianza: "Baja confianza",
  un_dominio: "Un solo dominio",
  json_malformado: "JSON malformado",
  red_caida: "Red caída",
  noticia_como_verdad: "Noticia tomada como verdad",
};

// Preguntas desde las noticias: la dieta de medios de cada agente.
const DIETAS = { izquierda: "solo medios de izquierda", derecha: "solo medios de derecha",
                 ambas: "medios de ambos lados", ninguna: "ningún medio" };

function cobertura(articulos) {
  const lado = l => articulos.filter(a => a.lean === l).map(a => `<li><a href="${esc(a.url)}" rel="noopener noreferrer"
      target="_blank">${esc(a.headline)}</a> <span class="tenue">— ${esc(a.outlet)}${a.via ? ` · vía ${esc(a.via)}` : ""}</span></li>`).join("")
    || `<li class="tenue">sin titulares</li>`;
  return `<div class="cobertura">
    <div><strong class="pequeno lado-izquierda">Izquierda</strong><ul class="pequeno">${lado("izquierda")}</ul></div>
    <div><strong class="pequeno lado-derecha">Derecha</strong><ul class="pequeno">${lado("derecha")}</ul></div>
  </div>`;
}

// Las preguntas con encuadre: dos titulares, cada persona ve uno.
const GRUPOS = { pro_si: "titular pro-SÍ", pro_no: "titular pro-NO" };

function titular(h, etiqueta = "") {
  if (!h) return "";
  const fuente = h.url
    ? `<a href="${esc(h.url)}" rel="noopener noreferrer" target="_blank">${esc(h.source)}</a>` : esc(h.source);
  return `<blockquote class="titular">${etiqueta ? `<span class="pequeno tenue">${esc(etiqueta)}</span><br>` : ""}
    «${esc(h.text)}» <span class="pequeno tenue">— ${fuente}</span></blockquote>`;
}

function esc(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function pct(p) {
  return `${Math.round(p * 100)} %`;
}

async function api(ruta, opciones = {}) {
  const r = await fetch(ruta, opciones);
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) {
    const error = new Error(cuerpo.detail?.[0]?.msg || cuerpo.detail || `error ${r.status}`);
    error.status = r.status;
    throw error;
  }
  return cuerpo;
}

// La clave del ponente viaja en el fragmento (#clave=…), que el navegador no envía al servidor ni a los logs.
const clave = new URLSearchParams(location.hash.slice(1)).get("clave") || "";

function cabeceras(extra = {}) {
  return clave ? { ...extra, "X-Presenter-Key": clave } : extra;
}

// Sin clave en un servidor que la exige, los controles del ponente no se muestran.
const esPonente = info => !(info.presenter_key_required && !clave);

// Sondeo sin solapes y solo con la pestaña visible. Una pestaña olvidada en segundo plano no gasta
// peticiones y, en la nube, deja de contar como «alguien mira»: la vigilia puede apagar los nodos.
function sondear(fn, ms) {
  let espera, enCurso = false;
  async function vuelta() {
    clearTimeout(espera);
    if (enCurso || document.hidden) return;
    enCurso = true;
    try { await fn(); } catch { /* el siguiente sondeo reintenta */ } finally { enCurso = false; }
    if (!document.hidden) espera = setTimeout(vuelta, ms);
  }
  document.addEventListener("visibilitychange", vuelta);
  vuelta();
}

// Solo toca el DOM si el contenido cambió: así un sondeo no cierra un <select> abierto ni roba el foco.
const pintados = new WeakMap();
function pintarSi(el, html) {
  if (pintados.get(el) === html) return;
  pintados.set(el, html);
  el.innerHTML = html;
}

function guardado(clave, valor) {
  try {
    if (valor === undefined) return localStorage.getItem(clave);
    localStorage.setItem(clave, valor);
  } catch { /* sin almacenamiento: la página funciona igual */ }
  return valor;
}

// Línea de precio con referencia en 50 %. `history` guarda P(SÍ) tras cada orden.
function sparkline(historia, ancho = 320, alto = 80) {
  const h = historia.length > 1 ? historia : [historia[0] ?? 0.5, historia[0] ?? 0.5];
  const x = i => (i / (h.length - 1)) * ancho;
  const y = p => alto - p * alto;
  const puntos = h.map((p, i) => `${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
  return `<svg class="spark" viewBox="0 0 ${ancho} ${alto}" preserveAspectRatio="none" role="img"
      aria-label="Evolución del precio del SÍ">
    <line x1="0" x2="${ancho}" y1="${alto / 2}" y2="${alto / 2}" class="spark-ref"/>
    <polyline points="${puntos}" class="spark-linea" vector-effect="non-scaling-stroke"/>
  </svg>`;
}
