// Lógica de index.html. Va en un archivo aparte para que la CSP prohíba scripts en línea.
let usuario = guardado("oraculo.usuario") || "";
// El token demuestra que el nombre es tuyo. Lo entrega el servidor una sola vez, al entrar.
let token = guardado("oraculo.token") || "";
let monto = Number(guardado("oraculo.monto")) || 50;
const respondidos = new Set(JSON.parse(guardado("oraculo.censo") || "[]"));
let sondeando = false;

document.getElementById("ingreso").addEventListener("submit", async e => {
  e.preventDefault();
  const aviso = document.getElementById("error-ingreso");
  aviso.textContent = "";
  try {
    const r = await api("/api/entrar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: document.getElementById("nombre").value.trim(),
                             code: document.getElementById("codigo").value.trim() }),
    });
    usuario = guardado("oraculo.usuario", r.name);
    token = guardado("oraculo.token", r.token);
    arrancar();
  } catch (err) {
    aviso.textContent = err.message;
  }
});

// La sala vive en memoria: si el servidor se reinicia, el token deja de valer y hay que volver a entrar.
function salir(motivo) {
  token = guardado("oraculo.token", "");
  document.getElementById("nombre").value = usuario;
  document.getElementById("panel").hidden = true;
  document.getElementById("ingreso").hidden = false;
  document.getElementById("como").hidden = false;
  document.getElementById("error-ingreso").textContent = motivo;
}

const conToken = (extra = {}) => ({ "X-User-Token": token, ...extra });

// Lo que tienes en juego, en créditos: cada acción ganadora paga 1.
function posicion(u, m) {
  const p = u.positions[m.id];
  if (!p || (p.YES < 0.01 && p.NO < 0.01)) return "";
  if (m.status !== "open") {
    const premio = p[m.outcome];
    return premio >= 0.01
      ? `<p class="resultado"><strong class="si">¡Acertaste!</strong> Recibiste ${premio.toFixed(0)} créditos.</p>`
      : `<p class="resultado">Esta vez no acertaste.</p>`;
  }
  const lados = ["YES", "NO"].filter(k => p[k] >= 0.01)
    .map(k => `si sale <strong class="${k === "YES" ? "si" : "no"}">${RESULTADO[k]}</strong>, recibes ${p[k].toFixed(0)} créditos`);
  return `<p class="pequeno">Tu apuesta: ${lados.join("; ")}.</p>`;
}

// Tu dieta de medios: los titulares de tu lado. No se dice qué lado es: el experimento es el
// titular, no la etiqueta. Al revelar, la proyección muestra los dos lados.
function tusNoticias(d) {
  if (!d || !d.articles.length) return "";
  return `<div class="titular"><span class="pequeno tenue">Tus noticias (la otra mitad de la sala lee otros
    medios; se revela al final)</span>
    <ul class="pequeno" style="margin:.3rem 0;padding-left:1.1rem">${d.articles.map(a => `<li>«${esc(a.headline)}»
      <span class="tenue">— ${esc(a.outlet)}</span></li>`).join("")}</ul></div>`;
}

// La revelación: lo que creía la sala frente a lo que encontró quien decide.
function revelacion(m) {
  const c = m.check;
  if (!c) return "";
  const sala = `La sala creía ${pct(c.price_yes)} SÍ`;
  if (c.outcome === "UNRESOLVED") {
    return `<p class="resultado pequeno"><strong class="pendiente">La IA buscó y dijo: aún no se sabe.</strong>
      No encontró pruebas suficientes, así que no adivina. Puedes seguir apostando.</p>`;
  }
  const quien = m.resolver === "oráculo" ? `la IA lo comprobó con ${c.sources} fuente(s)` : "y así fue";
  const acerto = Math.abs(c.price_yes - 0.5) < 0.02 ? ""
    : (c.outcome === "YES") === (c.price_yes > 0.5) ? " <strong>La sala acertó.</strong>" : " <strong>La sala se equivocó.</strong>";
  return `<p class="pequeno">${sala}; ${quien}.${acerto}</p>`;
}

function controles(m) {
  if (m.status !== "open") {
    return `<p class="resultado">Salió <strong class="grande-txt ${m.outcome === "YES" ? "si" : "no"}">${RESULTADO[m.outcome]}</strong></p>
      ${revelacion(m)}`;
  }
  const operar = `<div class="apostar">
      <button class="si" data-operar="YES" data-id="${m.id}">SÍ</button>
      <button class="no" data-operar="NO" data-id="${m.id}">NO</button>
    </div>`;
  if (m.kind !== "sala") return operar;
  const censo = respondidos.has(m.id)
    ? `<p class="pequeno tenue">Ya respondiste la encuesta privada. Nadie ve qué contestaste.</p>`
    : `<p class="pequeno"><strong>Encuesta privada:</strong> ¿y tú? Contesta la verdad sobre ti. Nadie verá qué dijiste.</p>
       <div class="fila">
         <button data-censo="true" data-id="${m.id}">Yo sí</button>
         <button data-censo="false" data-id="${m.id}">Yo no</button>
       </div>
       <p class="pequeno tenue">Y ahora apuesta: ¿qué dirá la mayoría?</p>`;
  return censo + operar;
}

async function pintar() {
  if (!token) return;
  let mercados, u;
  try {
    [mercados, u] = await Promise.all([
      api("/api/markets?resumen=true"),
      api(`/api/users/${encodeURIComponent(usuario)}`, { headers: conToken() }),
    ]);
  } catch (err) {
    if (err.status === 401) salir("La sala se reinició y tu sesión ya no vale: vuelve a entrar con el código de la pantalla.");
    throw err;
  }
  document.getElementById("quien").textContent = `Hola, ${u.name}`;
  document.getElementById("saldo").textContent = u.balance.toFixed(0);
  const abiertas = mercados.some(m => m.status === "open");
  pintarSi(document.getElementById("lista"), (abiertas ? `
    <div class="montos pequeno">Cuánto apuestas cada vez:
      ${[10, 50, 100, 250].map(n =>
        `<button data-monto="${n}" aria-pressed="${n === monto}">${n}</button>`).join("")}
    </div>` : "") + (mercados.length ? "" : `<p class="tenue">Todavía no hay preguntas. Aparecerán aquí solas en cuanto
      se abra la primera.</p>`)
    + ordenar(mercados).map(m => `
    <article class="tarjeta">
      <span class="chip">${esc(tipo(m).etiqueta)}</span>
      ${titular(u.headlines?.[m.id], "Tu titular (otras personas leen uno distinto; se revela al final)")}
      ${tusNoticias(u.diets?.[m.id])}
      <p class="pregunta">${esc(m.question)}</p>
      <p class="pequeno tenue" style="margin:0">La sala cree:</p>
      ${barra(m.prices.YES)}
      ${m.status === "open" ? revelacion(m) : ""}
      ${controles(m)}
      ${posicion(u, m)}
      <details class="pequeno"><summary>¿Cómo se decide?</summary>
        <p>${esc(m.criteria)}</p><p class="tenue">${esc(tipo(m).mide)}</p></details>
    </article>`).join(""));
}

document.getElementById("lista").addEventListener("click", async e => {
  const b = e.target.closest("button");
  if (!b || b.disabled) return;
  const error = document.getElementById("error");
  const hecho = document.getElementById("hecho");
  error.textContent = hecho.textContent = "";
  b.disabled = true;  // un doble toque no compra dos veces
  try {
    if (b.dataset.monto) {
      monto = Number(guardado("oraculo.monto", b.dataset.monto));
    } else if (b.dataset.operar) {
      const r = await api(`/api/markets/${b.dataset.id}/trade`, {
        method: "POST",
        headers: conToken({ "Content-Type": "application/json" }),
        body: JSON.stringify({ user: usuario, outcome: b.dataset.operar, amount: monto }),
      });
      hecho.textContent = `Listo: apostaste ${monto} a ${RESULTADO[b.dataset.operar]}. ` +
        `Si aciertas, recibes ${r.shares.toFixed(0)}. Ahora la sala cree ${pct(r.market.prices.YES)} SÍ.`;
    } else if (b.dataset.censo) {
      try {
        await api(`/api/markets/${b.dataset.id}/census`, {
          method: "POST",
          headers: conToken({ "Content-Type": "application/json" }),
          body: JSON.stringify({ user: usuario, answer: b.dataset.censo === "true" }),
        });
      } finally {
        respondidos.add(b.dataset.id);
        guardado("oraculo.censo", JSON.stringify([...respondidos]));
      }
    }
  } catch (err) {
    if (err.status === 401) salir("La sala se reinició y tu sesión ya no vale: vuelve a entrar con el código de la pantalla.");
    error.textContent = err.message;
  } finally {
    b.disabled = false;
  }
  pintar().catch(() => {});
});

api("/api/info").then(i => {
  document.getElementById("demanda").hidden = !["real", "plan", "ensayo"].includes(i.infra);
  for (const id of ["codigo", "codigo-etiqueta"]) document.getElementById(id).hidden = !i.room_code_required;
  document.getElementById("codigo").required = i.room_code_required;
}).catch(() => {});

function arrancar() {
  if (!usuario || !token) return;
  document.getElementById("ingreso").hidden = true;
  document.getElementById("como").hidden = true;
  document.getElementById("panel").hidden = false;
  document.getElementById("error-ingreso").textContent = "";
  if (sondeando) {
    pintar().catch(() => {});
    return;
  }
  sondeando = true;
  sondear(pintar, 3000);
}
arrancar();
