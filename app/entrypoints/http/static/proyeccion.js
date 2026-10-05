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

function veredicto(m) {
  const v = m.oracle;
  if (!v) return "";
  const fuentes = v.evidence.length
    ? `<p class="pequeno">Fuentes: ${[...new Set(v.evidence.map(e => esc(e.domain)))].join(" · ")}</p>` : "";
  return `<p class="contraste">${contraste(m)}</p>
    ${v.reasoning ? `<p class="pequeno tenue">${esc(v.reasoning)}</p>` : ""}
    ${fuentes}
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
  return `<div class="ponente fila">
    <button data-resolver="${m.id}" ${espera ? "disabled" : ""}>
      ${espera ? "Consultando…" : "Consultar al oráculo"}</button>
    <select data-fallo="${m.id}" aria-label="Inyectar un fallo">
      <option value="">sin fallo</option>
      ${Object.entries(FALLOS).map(([k, t]) => `<option value="${k}">fallo: ${t}</option>`).join("")}
    </select></div>`;
}

async function pintar() {
  const mercados = await api("/api/markets");
  const fallos = {};
  document.querySelectorAll("[data-fallo]").forEach(s => { fallos[s.dataset.fallo] = s.value; });
  abiertos.clear();
  document.querySelectorAll("details[data-intentos][open]").forEach(d => abiertos.add(d.dataset.intentos));
  document.getElementById("lista").innerHTML = mercados.map(m => {
    const p = m.prices.YES;
    const estado = m.status === "resolved"
      ? `<span class="chip">resuelto: ${RESULTADO[m.outcome]}</span>` : "";
    return `<article class="tarjeta">
      <div class="fila" style="margin:0"><span class="chip">${esc(tipo(m).etiqueta)}</span>${estado}</div>
      <p class="pregunta">${esc(m.question)}</p>
      <p class="mide tenue">${esc(tipo(m).mide)}</p>
      <p><span class="grande precio si">${pct(p)}</span> <span class="tenue">SÍ · abrió en 50 %
        · ${m.history.length - 1} órdenes</span></p>
      ${sparkline(m.history)}
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

api("/api/info").then(i => {
  info = i;
  document.getElementById("info").textContent =
    `Oráculo: ${i.oracle} (${i.model}) · infraestructura: ${i.infra} · revisión ${i.revision} · ` +
    `audiencia en ${location.origin}`;
  document.getElementById("sin-clave").hidden = !(i.presenter_key_required && !clave);
  pintar();
  setInterval(() => pintar().catch(() => {}), 2000);
});
