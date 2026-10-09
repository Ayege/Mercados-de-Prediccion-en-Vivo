// Lógica de proyeccion.html. Va en un archivo aparte para que la CSP prohíba scripts en línea.
let info = {};
const ocupado = new Set();  // el oráculo está consultando esta pregunta
const leyendo = new Set();  // los agentes están leyendo esta pregunta
const abiertos = new Set();

// El veredicto en una frase: qué dijo quien decide y si la sala había acertado.
function contraste(m) {
  const v = m.oracle;
  if (!v) return "";
  const sala = `La sala creía ${pct(v.price_yes)} SÍ.`;
  if (v.outcome === "UNRESOLVED") {
    return `<strong class="pendiente">Aún no se sabe.</strong> ${motivo(m)}
      <span class="tenue">${sala} La pregunta sigue abierta.</span>`;
  }
  const clase = v.outcome === "YES" ? "si" : "no";
  const fuentes = [...new Set(v.evidence.map(e => e.domain))];
  const quien = { censo: "La encuesta privada dice", "simulación": "La simulación dice",
                  "infraestructura real": "Lo medido en Google Cloud dice" }[m.resolver]
    || `La IA encontró la respuesta en ${fuentes.length} fuente(s) distintas:`;
  const acerto = Math.abs(v.price_yes - 0.5) < 0.02 ? "La sala no se inclinaba por ningún lado."
    : (v.outcome === "YES") === (v.price_yes > 0.5) ? "<strong>La sala acertó.</strong>" : "<strong>La sala se equivocó.</strong>";
  return `${quien} <strong class="${clase}">${RESULTADO[v.outcome]}</strong>. ${sala} ${acerto}`;
}

// El experimento de encuadre: qué apostó cada grupo según el titular que vio.
function encuadre(m) {
  const f = m.framing;
  if (!f) return "";
  const g = f.groups;
  const fila = k => {
    const x = g[k];
    const parte = x.yes_share == null ? "todavía sin apuestas" : `${pct(x.yes_share)} del dinero al SÍ`;
    return `<li><strong>${GRUPOS[k]}</strong>: les tocó a ${x.assigned}, ${x.traders} apostaron · ${parte}</li>`;
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
  const titulo = `<p class="pequeno"><strong>Cuatro bots también apuestan.</strong> Cada uno solo lee ciertos
    medios: uno de izquierda, uno de derecha, uno ambos y uno ninguno. ¿Cambia su apuesta según lo que lee?</p>`;
  if (!m.agents.length) {
    const boton = m.status === "open" && esPonente(info)
      ? `<button data-agentes="${m.id}" ${leyendo.has(m.id) ? "disabled" : ""}>
          ${leyendo.has(m.id) ? "Leyendo los titulares…" : "Que apuesten los bots"}</button>` : "";
    return `<div class="agentes">${titulo}${boton}</div>`;
  }
  const bloques = m.agents.map(a => {
    const barra = a.p == null ? `<p class="pequeno tenue">No pudo leer: no apostó.</p>` : `
      <div class="creencia" role="img" aria-label="Creyó ${pct(a.p)}; el precio estaba en ${pct(a.price_before)}">
        <span class="sala" style="left:calc(${a.price_before * 100}% - 2px)"></span>
        <span class="agente" style="left:calc(${a.p * 100}% - 2px)"></span></div>`;
    const apuesta = a.outcome
      ? `apostó ${a.stake.toFixed(0)} a <strong class="${a.outcome === "YES" ? "si" : "no"}">${RESULTADO[a.outcome]}</strong>`
      : "no apostó";
    const pnl = a.pnl == null ? ""
      : ` · <strong class="${a.pnl >= 0 ? "si" : "no"}">${a.pnl >= 0 ? "ganó" : "perdió"} ${Math.abs(a.pnl).toFixed(0)}</strong>`;
    return `<div class="agente-fila">
      <p class="pequeno" style="margin:0">Bot que lee <strong>${esc(DIETAS[a.diet])}</strong> (${a.read.length} titular(es)):
        cree <strong>${a.p == null ? "—" : pct(a.p)}</strong> SÍ · ${apuesta}${pnl}</p>
      ${barra}
      <p class="pequeno tenue" style="margin:0">${esc(a.reasoning)}</p></div>`;
  }).join("");
  return `<div class="agentes">${titulo}${bloques}
    <p class="pequeno tenue">Gris: lo que creía la sala cuando apostó el bot. Azul: lo que creyó el bot.</p></div>`;
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
    ? `<p>Fuentes: ${[...new Set(v.evidence.map(e => esc(e.domain)))].join(" · ")}</p>` : "";
  return `<p class="veredicto">${contraste(m)}</p>
    <details class="pequeno"><summary>Ver cómo lo decidió</summary>
      ${v.reasoning ? `<p>${esc(v.reasoning)}</p>` : ""}
      ${fuentes}
      ${lecturas(v)}
      <ol class="traza">${v.trace.map(t => `<li>${esc(t)}</li>`).join("")}</ol>
    </details>`;
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
  if (m.status !== "open" || !esPonente(info)) return "";
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
      <span class="pequeno tenue">${m.census_count} respuesta(s) a la encuesta</span>
      <button data-resolver="${m.id}" ${espera ? "disabled" : ""}>Cerrar con la encuesta</button></div>`;
  }
  const fallos = Object.entries(FALLOS).filter(([k]) => m.framing || !(k in (info.framing_faults || {})));
  const revelar = m.framing && !m.framing.revealed
    ? `<button data-revelar="${m.id}" title="Muestra los dos titulares en la proyección">Revelar titulares</button>` : "";
  return `<div class="ponente fila">
    <button data-resolver="${m.id}" ${espera ? "disabled" : ""}
      title="${m.framing ? "Consulta tres veces: sin titular y con cada uno. Solo acepta si coinciden" : ""}">
      ${espera ? "La IA está buscando…" : "Preguntar a la IA"}</button>${revelar}
    <details class="pequeno"><summary>Modo demo</summary>
      <select data-fallo="${m.id}" aria-label="Provocar un fallo en la próxima consulta">
        <option value="">sin fallo</option>
        ${fallos.map(([k, t]) => `<option value="${k}">provocar: ${t}</option>`).join("")}
      </select></details></div>`;
}

function tarjeta(m, destacada) {
  const estado = m.status === "resolved" ? `<span class="chip">salió ${RESULTADO[m.outcome]}</span>` : "";
  return `<article class="tarjeta${destacada ? " destacada" : ""}">
    <div class="fila" style="margin:0"><span class="chip">${esc(tipo(m).etiqueta)}${m.topic ? `: ${esc(m.topic)}` : ""}</span>${estado}</div>
    <p class="pregunta">${esc(m.question)}</p>
    ${destacada ? `<p class="mide tenue">${esc(tipo(m).mide)}</p>` : ""}
    <p class="tenue pequeno" style="margin:0">La sala cree · ${m.orders} apuesta(s)</p>
    ${barra(m.prices.YES)}
    ${destacada && m.orders ? sparkline(m.history) : ""}
    ${m.coverage.length ? cobertura(m.coverage) : ""}
    ${agentes(m)}
    ${encuadre(m)}
    ${veredicto(m)}
    ${intentos(m)}
    ${ponente(m)}
  </article>`;
}

async function pintar() {
  const mercados = await api("/api/markets");
  const fallos = {};
  document.querySelectorAll("[data-fallo]").forEach(s => { fallos[s.dataset.fallo] = s.value; });
  abiertos.clear();
  document.querySelectorAll("details[data-intentos][open]").forEach(d => abiertos.add(d.dataset.intentos));
  // Las preguntas del oráculo son el centro de la demo: van primero y en grande. El resto, compacto.
  const delOraculo = ordenar(mercados).filter(m => m.resolver === "oráculo");
  const otras = ordenar(mercados).filter(m => m.resolver !== "oráculo");
  const vacio = `<p class="tenue">Todavía no hay preguntas. ${esPonente(info) && info.news
    ? "Escribe un tema arriba y crea una desde las noticias de hoy." : "Aparecerán aquí en cuanto se abra la primera."}</p>`;
  pintarSi(document.getElementById("lista"), mercados.length ? `
    ${delOraculo.length ? `<h2>Lo decide la IA</h2>
      <p class="tenue">Ustedes apuestan sin buscar. Luego la IA busca la respuesta en internet: ¿quién acierta?</p>
      <div class="rejilla">${delOraculo.map(m => tarjeta(m, true)).join("")}</div>` : ""}
    ${otras.length ? `<h2 class="${delOraculo.length ? "secundario" : ""}">${delOraculo.length ? "Otras preguntas" : "Preguntas"}</h2>
      <div class="rejilla ${delOraculo.length ? "compacta" : ""}">${otras.map(m => tarjeta(m, !delOraculo.length)).join("")}</div>` : ""}` : vacio);
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
    leyendo.add(id);
    pintar();
    try {
      await api(`/api/markets/${id}/agentes`, { method: "POST", headers: cabeceras() });
    } catch (err) {
      document.getElementById("error").textContent = err.message;
    } finally {
      leyendo.delete(id);
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
    : d.accepted ? `<span class="chip si">lista para abrir</span>` : `<span class="chip no">no sirve: busca otro tema</span>`;
  const acciones = d.market_id ? "" : `<div class="fila">
    ${d.accepted ? `<button data-abrir="${d.id}">Abrir pregunta</button>` : ""}
    <button data-descartar="${d.id}">Descartar</button></div>`;
  return `<div class="borrador">
    <p class="pequeno tenue">Tema: ${esc(d.topic)} · ${esc(d.model)} ${estado}</p>
    ${d.question ? `<p class="pregunta">${esc(d.question)}</p><p class="pequeno tenue">${esc(d.criteria)}</p>` : ""}
    ${cobertura(d.articles)}
    <details><summary class="pequeno">Ver cómo se eligió</summary><ol class="traza">${d.trace.map(t => `<li>${esc(t)}</li>`).join("")}</ol></details>
    ${acciones}</div>`;
}

async function pintarNoticias() {
  const v = await api("/api/noticias", { headers: cabeceras() });
  const medios = v.media;
  const lados = l => medios.outlets.filter(o => o.lean === l).map(o => o.name).join(", ") || "ninguno";
  document.getElementById("medios").innerHTML = medios.ready
    ? `Medios${medios.rehearsal ? " <strong>de ensayo (ficticios)</strong>" : ""}: izquierda: ${esc(lados("izquierda"))} ·
       derecha: ${esc(lados("derecha"))}.${medios.source ? ` Clasificación: ${esc(medios.source)}.` : ""}
       Los titulares vienen de Google News, que los atribuye a cada medio; el modelo solo elige cuáles y propone la pregunta.`
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
      await api(`/api/noticias/borradores/${b.dataset.descartar}`, { method: "DELETE", headers: cabeceras() });
    }
  } catch (err) {
    error.textContent = err.message;
  }
  pintarNoticias().catch(() => {});
  pintar();
});

api("/api/info").then(i => {
  info = i;
  document.getElementById("url").textContent = location.host;
  document.getElementById("info").textContent =
    `Oráculo: ${i.oracle} (${i.model}) · infraestructura: ${i.infra} · revisión ${i.revision}`;
  const ponente = esPonente(i);
  document.getElementById("sin-clave").hidden = ponente;
  if (ponente && i.room_code_required) {
    api("/api/sala", { headers: cabeceras() })
      .then(s => { const c = document.getElementById("sala"); c.hidden = false; c.querySelector("strong").textContent = s.code; })
      .catch(() => {});
  }
  document.getElementById("noticias").hidden = !(ponente && i.news);
  if (ponente && i.news) pintarNoticias().catch(err => { document.getElementById("error").textContent = err.message; });
  sondear(pintar, 2000);
});
