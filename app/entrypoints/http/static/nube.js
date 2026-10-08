// Lógica de nube.html. Va en un archivo aparte para que la CSP prohíba scripts en línea.
const clave = new URLSearchParams(location.hash.slice(1)).get("clave") || "";
const ARQ = ["cooperativo", "agresivo", "previsor", "austero"];
const COLOR = i => `var(--serie-${i + 1})`;
const RECURSOS = { cpu: "cpu", almacenamiento: "almacenamiento", ancho_banda: "ancho de banda" };
const FALLA = { caida_nodo: "caída de nodo", latencia: "latencia", pico_demanda: "pico de demanda",
                rumor: "rumor alarmista" };

function texto(id, valor) { document.getElementById(id).textContent = valor; }

function cifras(v) {
  const e = v.forecast_error;
  const total = v.totals.served + v.totals.unmet;
  const items = [
    [`${v.tick}`, `tick · generación ${v.generation}`],
    [e.holt_winters == null ? "—" : `${(e.holt_winters * 100).toFixed(1)} %`,
     e.holt_winters == null ? "error de predicción" :
       `error de predicción · ingenuo ${(e.ingenuo_estacional * 100).toFixed(1)} %`],
    [`${v.contracts_won}/${v.contracts_total}`, "contratos cubiertos por coaliciones"],
    [`${v.incidents.length ? v.incidents[0].id : 0}`, `incidentes · ${v.false_positives} sin falla inyectada`],
    [total ? `${(v.totals.unmet / total * 100).toFixed(1)} %` : "—", "demanda no servida"],
  ];
  const c = document.getElementById("cifras");
  c.replaceChildren(...items.map(([n, t]) => {
    const d = document.createElement("div");
    d.className = "cifra";
    const s = document.createElement("strong"); s.textContent = n;
    const p = document.createElement("span"); p.textContent = t;
    d.append(s, p);
    return d;
  }));
}

function graficos(v) {
  lineas(document.getElementById("g-demanda"), {
    x: v.series.tick,
    series: [
      { nombre: "demanda real", valores: v.series.demand.cpu, color: COLOR(0) },
      { nombre: "predicción", valores: v.series.forecast.cpu, color: COLOR(1) },
    ],
    formato: n => n.toFixed(0),
  });
  lineas(document.getElementById("g-precios"), {
    x: v.series.tick,
    series: Object.entries(RECURSOS).map(([k, nombre], i) => ({ nombre, valores: v.series.price[k], color: COLOR(i) })),
  });
  const gens = v.generations;
  const cats = [...gens.map(g => `g${g.number}`), "ahora"];
  apiladas(document.getElementById("g-estrategias"), {
    categorias: cats,
    series: ARQ.map((a, i) => ({ nombre: a, color: COLOR(i),
      valores: [...gens.map(g => g.shares[a]), v.shares_now[a]] })),
    titulo: c => c === "ahora" ? `generación ${v.generation} (en curso)` : `generación ${c.slice(1)}`,
  });
  const rep = document.getElementById("replicador");
  if (gens.length) {
    const ult = gens[gens.length - 1];
    rep.textContent = `El replicador predijo ${Math.round(ult.predicted.cooperativo * 100)} % de cooperativos para la ` +
      `generación ${ult.number + 1}; hay ${Math.round(v.shares_now.cooperativo * 100)} %. ` +
      `Mejor de la generación ${ult.number}: ${ult.best} (${ult.best_fitness}).`;
  } else {
    rep.textContent = "";
  }
  tabla(document.getElementById("t-generaciones"), ["gen", ...ARQ, "predicho coop."],
    gens.map(g => [g.number, ...ARQ.map(a => `${Math.round(g.shares[a] * 100)} %`),
                   `${Math.round(g.predicted.cooperativo * 100)} %`]));
}

function tabla(contenedor, cabeza, filas) {
  const t = document.createElement("table");
  const h = t.createTHead().insertRow();
  cabeza.forEach(c => { const th = document.createElement("th"); th.textContent = c; h.appendChild(th); });
  const b = t.createTBody();
  filas.forEach(f => {
    const r = b.insertRow();
    f.forEach(c => {
      const td = r.insertCell();
      if (c instanceof Node) td.appendChild(c); else td.textContent = c;
    });
  });
  contenedor.replaceChildren(t);
}

function arquetipo(a) {
  const s = document.createElement("span");
  const m = document.createElement("span");
  m.className = "muestra";
  m.style.background = COLOR(ARQ.indexOf(a));
  s.append(m, document.createTextNode(a));
  return s;
}

function agentes(v) {
  tabla(document.getElementById("agentes"),
    ["agente", "región", "estrategia", "margen", "cooperación", "previsión", "credulidad", "ganancia", "nodo"],
    v.agents.map(a => [
      `${a.id} · g${a.born}`, a.region, arquetipo(a.archetype),
      `${a.markup.toFixed(2)} (${a.offset >= 0 ? "+" : ""}${a.offset.toFixed(1)})`,
      a.genome.cooperacion.toFixed(2), a.genome.prevision.toFixed(2), a.genome.credulidad.toFixed(2),
      a.fitness.toFixed(1),
      `${a.node.status} · ${a.node.latency.toFixed(0)} ms`,
    ]));
}

function li(lista, contenido) {
  const item = document.createElement("li");
  item.append(...contenido);
  lista.appendChild(item);
  return item;
}

function span(t, clase) {
  const s = document.createElement("span");
  if (clase) s.className = clase;
  s.textContent = t;
  return s;
}

function coaliciones(v) {
  texto("coaliciones-resumen", `${v.contracts_won} de ${v.contracts_total} contratos cubiertos.`);
  const l = document.getElementById("coaliciones");
  l.replaceChildren();
  for (const c of v.contracts.slice(0, 5)) {
    if (!c.members) {
      li(l, [span(`tick ${c.tick}: `), span("sin coalición", "pendiente"),
             span(` · ${c.willing} dispuesto(s), no alcanzó`, "tenue")]);
      continue;
    }
    const reparto = Object.entries(c.members).map(([a, s]) => `${a} ${s.toFixed(1)}`).join(" · ");
    li(l, [span(`tick ${c.tick}: `), span("cubierto", "si"), span(` · ${c.qty} cpu por ${c.payment} · Shapley: ${reparto}`, "tenue")]);
  }
}

function incidentes(v) {
  const l = document.getElementById("incidentes");
  l.replaceChildren();
  if (!v.incidents.length && !v.faults.length) li(l, [span("Sin incidentes. Inyecta una falla.", "tenue")]);
  for (const i of v.incidents.slice(0, 6)) {
    const origen = i.fault
      ? span(` · falla #${i.fault}, detectada ${i.detected_after} tick(s) después`, "tenue")
      : span(" · sin falla inyectada (falso positivo o carga real)", "pendiente");
    const estado = i.repaired != null && i.repaired <= v.tick
      ? span(` · reparado en el tick ${i.repaired}`, "si") : span(" · en curso", "pendiente");
    li(l, [span(`tick ${i.tick}: ${i.signal} (z ${i.z}) → ${i.action}`), origen, estado]);
  }
  for (const f of v.faults.filter(f => f.cleared == null)) {
    li(l, [span(`falla #${f.id} activa: ${FALLA[f.kind]}${f.target ? ` en ${f.target}` : ""} desde el tick ${f.tick}`, "no")]);
  }
}

function noticias(v) {
  const c = v.credulity;
  const ult = v.generations[v.generations.length - 1];
  texto("credulidad-resumen", `Credulidad media: ${c.start.toFixed(2)} al empezar, ${c.now.toFixed(2)} ahora` +
    (c.news_hit_rate == null ? "." : ` · las noticias acertaron el ${Math.round(c.news_hit_rate * 100)} % de las veces.`) +
    (ult ? ` Al cerrar la generación ${ult.number}: ${ult.credulity.toFixed(2)}.` : ""));
  const l = document.getElementById("noticias");
  l.replaceChildren();
  if (!v.news.length) li(l, [span("Todavía no llegó ninguna noticia.", "tenue")]);
  for (const n of v.news) {
    li(l, [
      span(`tick ${n.tick}: ${n.headline}${n.rumor ? " (rumor del ponente)" : ""} · `),
      n.true ? span("acertó: el pico llegó", "si") : span("falsa: el pico nunca llegó", "no"),
      ...(n.fresh ? [span(" · los crédulos la están creyendo ahora", "pendiente")] : []),
    ]);
  }
}

function topologia(v) {
  const t = v.topology;
  const d = document.getElementById("topologia");
  const replicas = Object.entries(t.replicas).map(([r, n]) => `${r} ×${n}`).join(" · ");
  const p = document.createElement("p");
  p.className = "pequeno";
  p.append(span("Actual: "), span(replicas), span(t.compliant ? " · cumple la política" : " · no cumple la política",
    t.compliant ? "si" : "no"));
  if (t.score) p.append(span(` · costo ${t.score.cost} · latencia ${t.score.latency} ms · valor ${t.score.value}`, "tenue"));
  d.replaceChildren(p);
  const l = document.getElementById("propuestas");
  l.replaceChildren();
  for (const pr of v.proposals) {
    const cab = [span(`#${pr.id} ${pr.source} (${pr.model}): `),
      span(pr.accepted ? (pr.adopted ? "aceptada y adoptada" : "aceptada, no mejora") : "rechazada",
           pr.accepted ? "si" : "no")];
    if (pr.score) cab.push(span(` · valor ${pr.score.value}`, "tenue"));
    const item = li(l, cab);
    if (pr.reasoning) item.appendChild(Object.assign(document.createElement("p"),
      { className: "pequeno tenue", textContent: pr.reasoning }));
    const ol = document.createElement("ol");
    ol.className = "traza";
    pr.trace.forEach(x => ol.appendChild(Object.assign(document.createElement("li"), { textContent: x })));
    item.appendChild(ol);
  }
}

const cabeceras = () => ({ "Content-Type": "application/json", ...(clave ? { "X-Presenter-Key": clave } : {}) });
let infraActiva = false;

// Qué hacer ahora, según el estado: la página le habla al ponente.
function pistaInfra(v) {
  const sondeados = v.nodes.filter(n => n.latency.length > 0);
  const listos = v.nodes.filter(n => n.latency.length >= 5 && !n.fault);
  const abierta = v.faults.find(f => !f.repaired);
  if (v.last_error) return "El controlador no puede leer Cloud Run: revisa el error de abajo y los permisos de oraculo-run.";
  if (!v.active && !v.nodes.length) {
    return v.mode === "real"
      ? "Actuación en pausa: nada existe todavía en Cloud Run. Activa la actuación para desplegar la topología adoptada."
      : `Actuación en pausa. En modo ${v.mode} no se crea nada real.`;
  }
  if (!v.active) return "Actuación en pausa: los nodos existen pero nadie los escala ni los repara. Actívala o apágalos.";
  if (!v.nodes.length) return "Activa la actuación… el primer ciclo crea los nodos. Cloud Run tarda unos 30 s en tenerlos listos.";
  if (v.nodes.some(n => n.reconciling)) return "Cloud Run está aplicando un cambio: la política no toca un nodo hasta que termine.";
  if (!sondeados.length) {
    return "Ningún nodo tiene instancias mínimas, así que no se sondean (cero instancias = cero costo). " +
      "Pide a la sala que abra la página de audiencia: su tráfico es la demanda.";
  }
  if (abierta) return `Falla real en ${abierta.region}: espera dos sondeos anómalos seguidos, la reparación y el primer sondeo sano.`;
  if (!listos.length) return "El detector está aprendiendo la latencia normal: hace falta 5 sondeos antes de inyectar una falla.";
  return `Listo para una falla real en ${listos.map(n => n.region).join(", ")}: usa «lento» o «caída» en la tabla de nodos.`;
}

function hora(t) {
  return t ? new Date(t * 1000).toLocaleTimeString() : "—";
}

async function pintarInfra(puedeControlar) {
  const v = await api("/api/infra", { headers: clave ? { "X-Presenter-Key": clave } : {} });
  const caja = document.getElementById("infra");
  if (v.mode === "apagado") { caja.hidden = true; return; }
  caja.hidden = false;
  infraActiva = v.active;
  const real = v.mode === "real";
  document.getElementById("honesto").textContent = real
    ? "Real sobre Cloud Run, con límites duros: la topología adoptada, el autoescalado, la reparación y el mercado " +
      "real (agentes con servicios propios, precios del catálogo de Cloud Billing, coaliciones que se ejecutan y " +
      "evolución con ganancia medida)." +
      (document.body.classList.contains("sin-lab") ? " Aquí no hay nada simulado: el laboratorio está apagado."
        : " La simulación de doce agentes de abajo sigue siendo un laboratorio.")
    : `Infraestructura en modo ${v.mode}: ${v.mode === "plan" ? "Cloud Run valida cada acción sin aplicarla" :
       "nube de ensayo en memoria, con precios reales de una foto del catálogo"}. Nada cobra.`;
  texto("infra-que", `Modo ${v.mode} (${v.gateway}) · actuación ${v.active ? "ACTIVA" : "en pausa"} · ` +
    `último ciclo ${hora(v.last_cycle)} · límites: ${v.policy.max_services} servicios, ` +
    `${v.policy.max_total_min} instancias mínimas en total, ${v.policy.max_max_per_region} máximas por región, ` +
    `un cambio de escala cada ${v.policy.seconds_between_changes} s por región. ` +
    `Si nadie mira esta página ${Math.round(v.ttl / 60)} min, la vigilia borra los nodos.`);
  document.getElementById("infra-controles").hidden = !puedeControlar;
  document.querySelector('[data-infra="actuar"]').textContent = v.active ? "Pausar actuación" : "Activar actuación";
  const notas = [...(v.last_error ? [v.last_error] : []), ...v.notes];
  texto("infra-notas", notas.join(" · "));
  texto("infra-pista", pistaInfra(v));
  document.getElementById("guia-real").hidden = false;
  document.getElementById("guia-apagar").hidden = false;
  document.getElementById("guia-mercado").hidden = !v.market;

  lineas(document.getElementById("g-demanda-real"), {
    x: v.rps.map(r => hora(r.t)),
    series: [
      { nombre: "req/s de la sala", valores: v.rps.map(r => r.real), color: COLOR(0) },
      { nombre: "predicción (Holt)", valores: v.rps.map(r => r.predicho), color: COLOR(1) },
    ],
    formato: n => n.toFixed(1),
    titulo: i => hora(v.rps[i].t),
  });

  const filas = v.nodes.map(n => {
    const ult = n.latency[n.latency.length - 1];
    const estado = n.reconciling ? "aplicando cambio" : n.ready ? "listo" : "arrancando";
    const acciones = document.createElement("span");
    if (puedeControlar && v.active && !n.fault && n.latency.length >= 5) {
      for (const [k, t] of [["latencia", "lento"], ["caida", "caída"]]) {
        const b = document.createElement("button");
        b.textContent = t;
        b.dataset.fallaReal = k;
        b.dataset.region = n.region;
        acciones.appendChild(b);
      }
    }
    return [n.region, `${n.min}–${n.max}`, estado, n.fault || "—", n.revision || "—",
            ult == null ? (n.last_status ? `error ${n.last_status}` : "—") : `${ult.toFixed(0)} ms`, acciones];
  });
  tabla(document.getElementById("infra-nodos"),
    ["nodo", "instancias", "estado", "falla", "revisión", "latencia", ""], filas);

  const l = document.getElementById("infra-log");
  l.replaceChildren();
  for (const e of v.log.slice(0, 8)) {
    const que = `${e.kind} ${e.region}${e.min != null ? ` ${e.min}–${e.max}` : ""}${e.fault ? ` (${e.fault})` : ""}`;
    li(l, [span(`${hora(e.at)} `, "tenue"), span(que), span(e.allowed ? " · ejecutada" : " · bloqueada",
      e.allowed ? "si" : "pendiente"), span(` · ${e.allowed ? e.result : e.why}`, "tenue")]);
  }
  if (!v.log.length) li(l, [span("Sin decisiones todavía.", "tenue")]);

  const inc = document.getElementById("infra-incidentes");
  inc.replaceChildren();
  for (const i of v.incidents.slice(0, 5)) {
    li(inc, [span(`${hora(i.at)} ${i.region} (z ${i.z})`),
      span(i.detected_after != null ? ` · detectado a los ${i.detected_after} s` : " · sin falla inyectada", "tenue"),
      i.repaired ? span(` · reparado a los ${i.repaired_after ?? "?"} s`, "si") : span(" · reparando", "pendiente")]);
  }
  for (const f of v.faults.filter(f => !f.repaired)) {
    li(inc, [span(`falla activa: ${f.kind} en ${f.region} desde ${hora(f.at)}`, "no")]);
  }
  if (!v.incidents.length && !v.faults.length) li(inc, [span("Sin incidentes reales.", "tenue")]);
  pintarMercado(v);
}

// Montos reales minúsculos: en millonésimas de dólar se leen mejor.
const micro = usd => usd == null ? "—" : `${(usd * 1e6).toFixed(2)} µUSD`;

function pintarMercado(v) {
  const m = v.market;
  const caja = document.getElementById("mercado");
  caja.hidden = !m;
  if (!m) return;
  const p = m.prices;
  texto("mercado-pista", m.error ? "El mercado no puede operar: " + m.error
    : !v.active ? "Actuación en pausa: los agentes no tienen servicios ni venden nada."
    : !m.cycles ? "Creando los servicios de los agentes en Cloud Run (unos 30 s). Sin instancia mínima no cuestan nada."
    : `Generación ${m.generation}, ciclo ${m.cycles}. Abre la página de audiencia: su tráfico es lo que se vende.`);
  texto("mercado-resumen", p ? `Precios: ${p.source}${p.fetched_at ? " (" + hora(p.fetched_at) + ")" : ""} · ` +
    `una petición en us-east1 cuesta ${micro(p.request_cost["us-east1"])} · una hora caliente, ` +
    `${(p.warm_hour["us-east1"] * 100).toFixed(2)} centavos · gasto real del mercado: ${micro(m.spend_usd)} · ` +
    `tope: ${m.budget.max_requests} peticiones por ciclo, ${m.budget.max_warm} agente(s) caliente(s)` : "Sin precios todavía.");
  tabla(document.getElementById("mercado-agentes"),
    ["agente", "región", "caliente", "margen", "pide", "a tiempo · tarde · error", "p50", "ingreso", "costo real", "ganancia"],
    m.agents.map(a => [
      `${a.id} · g${a.born}`, a.region,
      `${a.genome.warm ? "sí" : "no"}${a.service && a.service.warm !== a.genome.warm ? " (aplicando)" : ""}`,
      a.markup.toFixed(2), micro(a.ask_usd), `${a.served} · ${a.late} · ${a.failed}`,
      a.p50_ms == null ? "—" : `${a.p50_ms} ms`, micro(a.revenue_usd), micro(a.cost_usd), micro(a.profit_usd),
    ]));
  const l = document.getElementById("mercado-intercambios");
  l.replaceChildren();
  for (const t of m.trades.slice(0, 4)) {
    const vendidas = Object.values(t.fills).reduce((x, y) => x + y, 0);
    const quien = Object.entries(t.fills).map(([k, n]) => `${k}×${n}`).join(" ");
    li(l, [span(`${hora(t.at)} `, "tenue"),
      span(`demanda real ${t.demand} → vendidas ${vendidas}${t.demand > vendidas ? " (tope de costo)" : ""}`),
      span(` a ${micro(t.price)} · ${quien}`, "tenue")]);
  }
  for (const c of m.contracts.slice(0, 3)) {
    li(l, [span(`${hora(c.at)} contrato de ${c.qty} en dos regiones: `), span(c.detail,
      c.fulfilled ? "si" : c.fulfilled === false ? "no" : "pendiente")]);
  }
  if (!m.trades.length && !m.contracts.length) li(l, [span("Sin intercambios todavía.", "tenue")]);
  const g = document.getElementById("mercado-generaciones");
  g.replaceChildren();
  for (const x of m.generations.slice().reverse()) {
    li(g, [span(`generación ${x.number}: `), span(`${Math.round(x.warm_share * 100)} % calientes · mejor ${x.best}`, "tenue")]);
  }
  if (!m.generations.length) li(g, [span(`La primera generación cierra a los ${m.budget.generation_cycles} ciclos.`, "tenue")]);
}

document.getElementById("infra").addEventListener("click", async e => {
  const b = e.target.closest("button");
  if (!b) return;
  const error = document.getElementById("error");
  error.textContent = "";
  let ruta, cuerpo;
  if (b.dataset.infra === "actuar") ruta = `/api/infra/actuar?activo=${!infraActiva}`;
  else if (b.dataset.infra === "ciclo") ruta = "/api/infra/ciclo";
  else if (b.dataset.infra === "apagar") {
    if (!confirm("¿Borrar todos los nodos reales y pausar la actuación?")) return;
    ruta = "/api/infra/apagar";
  } else if (b.dataset.fallaReal) {
    ruta = "/api/infra/fallas";
    cuerpo = JSON.stringify({ region: b.dataset.region, kind: b.dataset.fallaReal });
  } else return;
  b.disabled = true;
  try {
    await api(ruta, { method: "POST", headers: cabeceras(), body: cuerpo });
  } catch (err) {
    error.textContent = err.message;
  } finally {
    b.disabled = false;
    pintar();
  }
});

let puedeControlar = false;

async function pintar() {
  pintarInfra(puedeControlar).catch(() => {});
  const v = await api("/api/nube");
  document.body.classList.toggle("sin-lab", !v.lab);
  texto("estado", (v.lab ? `${v.running ? "Corriendo" : "En pausa"} · semilla ${v.seed} · ` : "") +
    `generador de topologías: ${v.generator.name} (${v.generator.model})`);
  topologia(v);
  if (!v.lab) return;
  cifras(v);
  graficos(v);
  agentes(v);
  coaliciones(v);
  incidentes(v);
  noticias(v);
}

document.getElementById("controles").addEventListener("click", async e => {
  const b = e.target.closest("button");
  if (!b) return;
  const error = document.getElementById("error");
  error.textContent = "";
  const opciones = { method: "POST", headers: { "Content-Type": "application/json", ...(clave ? { "X-Presenter-Key": clave } : {}) } };
  let ruta;
  if (b.dataset.accion === "avanzar") ruta = `/api/nube/avanzar?n=${b.dataset.n}`;
  else if (b.dataset.accion) ruta = `/api/nube/${b.dataset.accion}`;
  else if (b.dataset.falla) { ruta = "/api/nube/fallas"; opciones.body = JSON.stringify({ kind: b.dataset.falla }); }
  else if (b.dataset.topologia) ruta = `/api/nube/topologias?fuente=${b.dataset.topologia}`;
  b.disabled = true;
  try {
    await api(ruta, opciones);
  } catch (err) {
    error.textContent = err.message;
  } finally {
    b.disabled = false;
    pintar();
  }
});

api("/api/info").then(i => {
  puedeControlar = !(i.presenter_key_required && !clave);
  document.getElementById("sin-clave").hidden = puedeControlar;
  document.getElementById("enlace-proyeccion").href = `proyeccion.html${location.hash}`;
  document.getElementById("controles").hidden = !puedeControlar;
  pintar();
  setInterval(() => pintar().catch(() => {}), 1500);
});
