// Utilidades compartidas por la vista de la audiencia y la de proyección.

const TIPOS = {
  presente: {
    etiqueta: "Ya ocurrió",
    mide: "La respuesta ya existe y es verificable. Nadie aquí la sabe con certeza: el precio agrega lo que la sala sabe en conjunto.",
  },
  futuro: {
    etiqueta: "Aún no tiene respuesta",
    mide: "Hoy es irresoluble a propósito. Lo correcto es que el oráculo diga SIN RESOLVER.",
  },
  sala: {
    etiqueta: "Información de la sala",
    mide: "La respuesta está repartida entre ustedes y ningún buscador la tiene. La resuelve un censo privado, no el oráculo.",
  },
  simulacion: {
    etiqueta: "Nube simulada",
    mide: "Nadie sabe qué harán los agentes: el comportamiento es emergente. La resuelve el código de la simulación, no un modelo ni la sala.",
  },
  real: {
    etiqueta: "Nube real · Cloud Run",
    mide: "Se resuelve con lo que pase de verdad en Google Cloud: una falla real, un detector real y una reparación real, cronometrados.",
  },
};

// El tipo que se muestra: las preguntas que resuelve la infraestructura real tienen el suyo.
function tipo(m) {
  return TIPOS[m.resolver === "infraestructura real" ? "real" : m.kind];
}

const RESULTADO = { YES: "SÍ", NO: "NO", UNRESOLVED: "SIN RESOLVER" };

const FALLOS = {
  baja_confianza: "Baja confianza",
  un_dominio: "Un solo dominio",
  json_malformado: "JSON malformado",
  red_caida: "Red caída",
  noticia_como_verdad: "Noticia tomada como verdad",
};

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
  if (!r.ok) throw new Error(cuerpo.detail?.[0]?.msg || cuerpo.detail || `error ${r.status}`);
  return cuerpo;
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
