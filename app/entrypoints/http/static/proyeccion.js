// Lógica de proyeccion.html. Va en un archivo aparte para que la CSP prohíba scripts en línea.
// La clave del ponente viaja en el fragmento (#clave=…), que el navegador no envía al servidor ni a los logs.
const clave = new URLSearchParams(location.hash.slice(1)).get("clave") || "";
let info = {};
const ocupado = new Set();
const abiertos = new Set();

function cabeceras() {
  return clave ? { "X-Presenter-Key": clave } : {};
}

function contraste(m) {
  const v = m.oracle;
  if (!v) return "";
  const creencia = `La sala decía <strong>${pct(v.price_yes)} SÍ</strong>`;
  const fuentes = new Set(v.evidence.map(e => e.domain)).size;
  if (v.outcome === "UNRESOLVED") {
    const quien = { censo: "El censo", "simulación": "La simulación",
                    "infraestructura real": "Cloud Run" }[m.resolver] || "El oráculo";
    return `${creencia}. ${quien} <strong class="pendiente">se negó a resolver</strong>.`;
  }
  const clase = v.outcome === "YES" ? "si" : "no";
  const juez = { censo: "el censo", "simulación": "la simulación",
                 "infraestructura real": "lo medido en Cloud Run" }[m.resolver];
  const base = juez
    ? `${juez} dice <strong class="${clase}">${RESULTADO[v.outcome]}</strong>`
    : `el oráculo dice <strong class="${clase}">${RESULTADO[v.outcome]}</strong> con ${fuentes} fuente(s)`;
  // ¿Se movió el precio hacia la respuesta desde la apertura en 50 %?
  const haciaVerdad = v.outcome === "YES" ? v.price_yes > 0.5 : v.price_yes < 0.5;
  const lectura = Math.abs(v.price_yes - 0.5) < 0.02
    ? "El precio no se movió de la apertura."
    : haciaVerdad ? "El precio se había movido hacia la respuesta." : "El precio se había movido en contra.";
  return `${creencia}; ${base}. <span class="tenue">${lectura}</span>`;
}

// El experimento de encuadre: qué apostó cada grupo según el titular que vio.
function encuadre(m) {
  const f = m.framing;
  if (!f) return "";
  const g = f.groups;
  const fila = k => {
    const x = g[k];
    const parte = x.yes_share == null ? "todavía sin apuestas" : `${pct(x.yes_share)} del dinero al SÍ`;
    return `<li><strong>${GRUPOS[k]}</strong>: ${x.exposed} lo vieron, ${x.traders} apostaron · ${parte}</li>`;
  };
  let lectura = "";
  if (g.pro_si.yes_share != null && g.pro_no.yes_share != null) {
    const d = Math.round((g.pro_si.yes_share - g.pro_no.yes_share) * 100);
    const sentido = d === 0 ? "Los dos grupos apostaron igual: el titular no movió a esta sala."
      : d > 0 ? `Quienes leyeron el titular pro-SÍ pusieron <strong>${d} puntos más</strong> al SÍ, como empuja su titular.`
      : `Quienes leyeron el titular pro-SÍ pusieron <strong>${-d} puntos menos</strong> al SÍ: al revés de lo que empuja su titular.`;
    lectura = `<p class="pequeno">${sentido} La asignación fue al azar, así que en esta sala la diferencia no la
      explica quién es cada grupo. Con tan pocas personas puede ser ruido.</p>`;
  }
  const titulares = f.headlines
    ? titular(f.headlines.pro_si, GRUPOS.pro_si) + titular(f.headlines.pro_no, GRUPOS.pro_no)
    : `<p class="pequeno tenue">Los titulares siguen ocultos: la sala los está leyendo.</p>`;
  return `<div class="encuadre"><p class="pequeno"><strong>Encuadre</strong> · la sala está dividida al azar en dos
    grupos; cada uno lee un titular distinto sobre el mismo hecho.</p>
    <ul class="intentos">${fila("pro_si")}${fila("pro_no")}</ul>${lectura}${titulares}</div>`;
}

// Qué leyó, creyó y apostó cada agente según su dieta de medios.
function agentes(m) {
  if (!m.coverage.length) return "";
  const titulo = `<p class="pequeno"><strong>Agentes y dieta de medios</strong> · cuatro agentes leen la misma
    cobertura, cada uno solo lo que su dieta le permite, y apuestan en este mercado.</p>`;
  if (!m.agents.length) {
    const boton = m.status === "open" && !(info.presenter_key_required && !clave)
      ? `<button data-agentes="${m.id}" ${ocupado.has(m.id) ? "disabled" : ""}>
          ${ocupado.has(m.id) ? "Leyendo…" : "Que opinen los agentes"}</button>` : "";
    return `<div class="agentes">${titulo}<p class="pequeno tenue">Todavía no han leído nada.</p>${boton}</div>`;
  }
  const bloques = m.agents.map(a => {
    const barra = a.p == null ? `<p class="pequeno tenue">No pudo leer: no apostó.</p>` : `
      <div class="creencia" role="img" aria-label="Creyó ${pct(a.p)}; el precio estaba en ${pct(a.price_before)}">
        <span class="sala" style="left:calc(${a.price_before * 100}% - 2px)"></span>
        <span class="agente" style="left:calc(${a.p * 100}% - 2px)"></span></div>`;
    const apuesta = a.outcome
      ? `compró <strong class="${a.outcome === "YES" ? "si" : "no"}">${RESULTADO[a.outcome]}</strong> por ${a.stake.toFixed(0)}`
      : "no apostó";
    const pnl = a.pnl == null ? ""
      : ` · <strong class="${a.pnl >= 0 ? "si" : "no"}">${a.pnl >= 0 ? "ganó" : "perdió"} ${Math.abs(a.pnl).toFixed(0)}</strong>`;
    return `<div class="agente-fila">
      <p class="pequeno" style="margin:0"><strong>${esc(DIETAS[a.diet])}</strong> · leyó ${a.read.length} titular(es) ·
        cree <strong>${a.p == null ? "—" : pct(a.p)}</strong> SÍ (el precio estaba en ${pct(a.price_before)}) · ${apuesta}${pnl}</p>
      ${barra}
      <p class="pequeno tenue" style="margin:0">${esc(a.reasoning)}</p></div>`;
  }).join("");
  return `<div class="agentes">${titulo}${bloques}
    <p class="pequeno tenue">En cada barra, gris es el precio que encontró el agente y azul lo que creyó. Apostaron
    uno tras otro, comprando hasta llevar el precio a su creencia, así que el último fija el precio que ve la sala.</p></div>`;
}

// Cómo leyó el modelo la misma pregunta con cada titular.
function lecturas(v) {
  if (!v.framing) return "";
  const nombre = { neutral: "sin titular", pro_si: "con el titular pro-SÍ", pro_no: "con el titular pro-NO" };
  return `<ul class="intentos">${Object.entries(v.framing).map(([k, x]) => `
    <li>${nombre[k]}: <strong class="${x.outcome === "YES" ? "si" : x.outcome === "NO" ? "no" : "pendiente"}">
      ${RESULTADO[x.outcome]}</strong> <span class="tenue">(confianza ${x.confidence.toFixed(2)})</span></li>`).join("")}
  </ul>`;
}

function veredicto(m) {
  const v = m.oracle;
  if (!v) return "";
  const fuentes = v.evidence.length
    ? `<p class="pequeno">Fuentes: ${[...new Set(v.evidence.map(e => esc(e.domain)))].join(" · ")}</p>` : "";
  return `<p class="contraste">${contraste(m)}</p>
    ${v.reasoning ? `<p class="pequeno tenue">${esc(v.reasoning)}</p>` : ""}
    ${fuentes}
    ${lecturas(v)}
    <ol class="traza">${v.trace.map(t => `<li>${esc(t)}</li>`).join("")}</ol>`;
}

function intentos(m) {
  if (m.attempts.length < 2) return "";
  return `<details data-intentos="${m.id}" ${abiertos.has(m.id) ? "open" : ""}><summary class="pequeno">Consultas (${m.attempts.length})</summary>
    <ul class="intentos">${m.attempts.map(a => `
      <li><strong class="${a.outcome === "UNRESOLVED" ? "pendiente" : a.outcome === "YES" ? "si" : "no"}">
        ${RESULTADO[a.outcome]}</strong>
        con la sala en ${pct(a.price_yes)}${a.fault ? ` · fallo: ${esc(FALLOS[a.fault])}` : ""}
        <span class="tenue">— ${esc(a.reason)}</span></li>`).join("")}
    </ul></details>`;
}

function ponente(m) {
  if (m.status !== "open" || (info.presenter_key_required && !clave)) return "";
  const espera = ocupado.has(m.id);
  if (m.kind === "simulacion") {
    return `<div class="ponente fila">
      <a class="pequeno" href="nube.html${location.hash}">Ver la nube</a>
      <button data-resolver="${m.id}" ${espera ? "disabled" : ""}
        title="Si todavía no se puede decidir, queda SIN RESOLVER y el mercado sigue abierto">
        ${m.resolver === "infraestructura real" ? "Resolver con lo medido en Cloud Run" : "Resolver con la simulación"}
      </button></div>`;
  }
  if (m.kind === "sala") {
    return `<div class="ponente fila">
      <span class="pequeno tenue">${m.census_count} respuesta(s) al censo</span>
      <button data-resolver="${m.id}" ${espera ? "disabled" : ""}>Cerrar con el censo</button></div>`;
  }
  const fallos = Object.entries(FALLOS).filter(([k]) => m.framing || !(k in (info.framing_faults || {})));
  const revelar = m.framing && !m.framing.revealed
    ? `<button data-revelar="${m.id}" title="Muestra los dos titulares en la proyección">Revelar titulares</button>` : "";
  return `<div class="ponente fila">
    <button data-resolver="${m.id}" ${espera ? "disabled" : ""}
      title="${m.framing ? "Consulta tres veces: sin titular y con cada uno. Solo acepta si coinciden" : ""}">
      ${espera ? "Consultando…" : "Consultar al oráculo"}</button>
    <select data-fallo="${m.id}" aria-label="Inyectar un fallo">
      <option value="">sin fallo</option>
      ${fallos.map(([k, t]) => `<option value="${k}">fallo: ${t}</option>`).join("")}
    </select>${revelar}</div>`;
}

async function pintar() {
  const mercados = await api("/api/markets");
  const fallos = {};
  document.querySelectorAll("[data-fallo]").forEach(s => { fallos[s.dataset.fallo] = s.value; });
  abiertos.clear();
  document.querySelectorAll("details[data-intentos][open]").forEach(d => abiertos.add(d.dataset.intentos));
  document.getElementById("lista").innerHTML = ordenar(mercados).map(m => {
    const p = m.prices.YES;
    const estado = m.status === "resolved"
      ? `<span class="chip">resuelto: ${RESULTADO[m.outcome]}</span>` : "";
    return `<article class="tarjeta">
      <div class="fila" style="margin:0"><span class="chip">${esc(tipo(m).etiqueta)}${m.topic ? `: ${esc(m.topic)}` : ""}</span>${estado}</div>
      <p class="pregunta">${esc(m.question)}</p>
      <p class="mide tenue">${esc(tipo(m).mide)}</p>
      <p><span class="grande precio si">${pct(p)}</span> <span class="tenue">SÍ · abrió en 50 %
        · ${m.history.length - 1} órdenes</span></p>
      ${sparkline(m.history)}
      ${m.coverage.length ? cobertura(m.coverage) : ""}
      ${agentes(m)}
      ${encuadre(m)}
      ${veredicto(m)}
      ${intentos(m)}
      ${ponente(m)}
    </article>`;
  }).join("");
  for (const [id, valor] of Object.entries(fallos)) {
    const s = document.querySelector(`[data-fallo="${id}"]`);
    if (s) s.value = valor;
  }
}

document.getElementById("lista").addEventListener("click", async e => {
  const g = e.target.closest("[data-agentes]");
  if (g) {
    const id = g.dataset.agentes;
    document.getElementById("error").textContent = "";
    ocupado.add(id);
    pintar();
    try {
      await api(`/api/markets/${id}/agentes`, { method: "POST", headers: cabeceras() });
    } catch (err) {
      document.getElementById("error").textContent = err.message;
    } finally {
      ocupado.delete(id);
      pintar();
    }
    return;
  }
  const r = e.target.closest("[data-revelar]");
  if (r) {
    try {
      await api(`/api/markets/${r.dataset.revelar}/revelar`, { method: "POST", headers: cabeceras() });
    } catch (err) {
      document.getElementById("error").textContent = err.message;
    }
    pintar();
    return;
  }
  const b = e.target.closest("[data-resolver]");
  if (!b) return;
  const id = b.dataset.resolver;
  const fallo = document.querySelector(`[data-fallo="${id}"]`)?.value;
  const error = document.getElementById("error");
  error.textContent = "";
  ocupado.add(id);
  pintar();
  try {
    await api(`/api/markets/${id}/resolve${fallo ? `?fault=${fallo}` : ""}`, {
      method: "POST", headers: cabeceras(),
    });
  } catch (err) {
    error.textContent = err.message;
  } finally {
    ocupado.delete(id);
    pintar();
  }
});

// --- panel del ponente: preguntas desde las noticias -----------------------------
function borrador(d) {
  const estado = d.market_id ? `<span class="chip">abierta</span>`
    : d.accepted ? `<span class="chip si">la política la acepta</span>` : `<span class="chip no">rechazada</span>`;
  const acciones = d.market_id ? "" : `<div class="fila">
    ${d.accepted ? `<button data-abrir="${d.id}">Abrir pregunta</button>` : ""}
    <button data-descartar="${d.id}">Descartar</button></div>`;
  return `<div class="borrador">
    <p class="pequeno tenue">Tema: ${esc(d.topic)} · ${esc(d.model)} ${estado}</p>
    ${d.question ? `<p class="pregunta">${esc(d.question)}</p><p class="pequeno tenue">${esc(d.criteria)}</p>` : ""}
    ${cobertura(d.articles)}
    <details><summary class="pequeno">Traza</summary><ol class="traza">${d.trace.map(t => `<li>${esc(t)}</li>`).join("")}</ol></details>
    ${acciones}</div>`;
}

async function pintarNoticias() {
  const v = await api("/api/noticias", { headers: cabeceras() });
  const medios = v.media;
  const lados = l => medios.outlets.filter(o => o.lean === l).map(o => o.name).join(", ") || "ninguno";
  document.getElementById("medios").innerHTML = medios.ready
    ? `Lista de medios${medios.rehearsal ? " <strong>de ensayo (ficticios)</strong>" : ""}: izquierda: ${esc(lados("izquierda"))} ·
       derecha: ${esc(lados("derecha"))}.${medios.source ? ` Clasificación: ${esc(medios.source)}.` : ""}
       El modelo propone la pregunta; los titulares se verifican en la página de cada medio.`
    : `<span class="pendiente">Falta la lista de medios.</span> Define al menos un medio de izquierda y uno de derecha
       en <code>app/medios.json</code>, con la fuente de cada clasificación.`;
  document.getElementById("borradores").innerHTML = v.drafts.map(borrador).join("");
}

document.getElementById("buscar-noticias").addEventListener("submit", async e => {
  e.preventDefault();
  const boton = e.target.querySelector("button");
  const error = document.getElementById("error");
  error.textContent = "";
  boton.disabled = true;
  boton.textContent = "Buscando…";
  try {
    await api("/api/noticias/borradores", {
      method: "POST", headers: { "Content-Type": "application/json", ...cabeceras() },
      body: JSON.stringify({ topic: document.getElementById("tema").value.trim() }),
    });
  } catch (err) {
    error.textContent = err.message;
  } finally {
    boton.disabled = false;
    boton.textContent = "Buscar noticias";
    pintarNoticias().catch(() => {});
  }
});

document.getElementById("borradores").addEventListener("click", async e => {
  const b = e.target.closest("button");
  if (!b) return;
  const error = document.getElementById("error");
  error.textContent = "";
  try {
    if (b.dataset.abrir) {
      await api(`/api/noticias/borradores/${b.dataset.abrir}/abrir`, { method: "POST", headers: cabeceras() });
    } else if (b.dataset.descartar) {
      await fetch(`/api/noticias/borradores/${b.dataset.descartar}`, { method: "DELETE", headers: cabeceras() });
    }
  } catch (err) {
    error.textContent = err.message;
  }
  pintarNoticias().catch(() => {});
  pintar();
});

api("/api/info").then(i => {
  info = i;
  document.getElementById("info").textContent =
    `Oráculo: ${i.oracle} (${i.model}) · infraestructura: ${i.infra} · revisión ${i.revision} · ` +
    `audiencia en ${location.origin}`;
  document.getElementById("sin-clave").hidden = !(i.presenter_key_required && !clave);
  const ponente = !(i.presenter_key_required && !clave);
  document.getElementById("noticias").hidden = !(ponente && i.news);
  if (ponente && i.news) pintarNoticias().catch(err => { document.getElementById("error").textContent = err.message; });
  pintar();
  setInterval(() => pintar().catch(() => {}), 2000);
});
