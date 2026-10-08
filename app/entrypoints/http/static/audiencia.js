// Lógica de index.html. Va en un archivo aparte para que la CSP prohíba scripts en línea.
let usuario = guardado("oraculo.usuario") || "";
// El token demuestra que el nombre es tuyo. Lo entrega el servidor una sola vez, al entrar.
let token = guardado("oraculo.token") || "";
let monto = Number(guardado("oraculo.monto")) || 50;
const respondidos = new Set(JSON.parse(guardado("oraculo.censo") || "[]"));

document.getElementById("ingreso").addEventListener("submit", async e => {
  e.preventDefault();
  const aviso = document.getElementById("error-ingreso");
  aviso.textContent = "";
  try {
    const r = await api("/api/entrar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: document.getElementById("nombre").value.trim() }),
    });
    usuario = guardado("oraculo.usuario", r.name);
    token = guardado("oraculo.token", r.token);
    arrancar();
  } catch (err) {
    aviso.textContent = err.message;
  }
});

const conToken = (extra = {}) => ({ "X-User-Token": token, ...extra });

function posicion(u, id) {
  const p = u.positions[id];
  if (!p || (p.YES < 0.01 && p.NO < 0.01)) return "";
  return `<p class="pequeno tenue">Tienes ${p.YES.toFixed(1)} acciones SÍ · ${p.NO.toFixed(1)} acciones NO</p>`;
}

function controles(m) {
  if (m.status !== "open") {
    return `<p>Resuelto: <strong class="${m.outcome === "YES" ? "si" : "no"}">${RESULTADO[m.outcome]}</strong></p>`;
  }
  const operar = `<div class="fila">
      <button class="si" data-operar="YES" data-id="${m.id}">Comprar SÍ</button>
      <button class="no" data-operar="NO" data-id="${m.id}">Comprar NO</button>
    </div>`;
  if (m.kind !== "sala") return operar;
  const censo = respondidos.has(m.id)
    ? `<p class="pequeno tenue">Ya respondiste el censo. Tu respuesta es privada.</p>`
    : `<p class="pequeno">Censo privado: ¿y tú? Responde la verdad sobre ti; no se publica quién dijo qué.</p>
       <div class="fila">
         <button data-censo="true" data-id="${m.id}">Sí, yo sí</button>
         <button data-censo="false" data-id="${m.id}">Yo no</button>
       </div>`;
  return censo + operar;
}

async function pintar() {
  const [mercados, u] = await Promise.all([
    api("/api/markets"), api(`/api/users/${encodeURIComponent(usuario)}`, { headers: conToken() }),
  ]);
  document.getElementById("quien").textContent = u.name;
  document.getElementById("saldo").textContent = u.balance.toFixed(0);
  document.getElementById("lista").innerHTML = `
    <div class="fila pequeno">Monto por orden:
      ${[10, 50, 100, 250].map(n =>
        `<button data-monto="${n}" ${n === monto ? "disabled" : ""}>${n}</button>`).join("")}
    </div>` + mercados.map(m => `
    <article class="tarjeta">
      <span class="chip">${esc(tipo(m).etiqueta)}</span>
      ${titular(u.headlines?.[m.id], "Titular que te tocó: la sala ve dos titulares distintos y se revelan al final")}
      <p class="pregunta">${esc(m.question)}</p>
      <p class="pequeno tenue">${esc(m.criteria)}</p>
      ${m.kind === "simulacion" ? `<p class="pequeno tenue">${esc(tipo(m).mide)}</p>` : ""}
      <p class="precio"><span class="si">SÍ ${pct(m.prices.YES)}</span> ·
        <span class="no">NO ${pct(m.prices.NO)}</span></p>
      ${controles(m)}
      ${posicion(u, m.id)}
    </article>`).join("");
}

document.getElementById("lista").addEventListener("click", async e => {
  const b = e.target.closest("button");
  if (!b) return;
  const error = document.getElementById("error");
  error.textContent = "";
  try {
    if (b.dataset.monto) {
      monto = Number(guardado("oraculo.monto", b.dataset.monto));
    } else if (b.dataset.operar) {
      await api(`/api/markets/${b.dataset.id}/trade`, {
        method: "POST",
        headers: conToken({ "Content-Type": "application/json" }),
        body: JSON.stringify({ user: usuario, outcome: b.dataset.operar, amount: monto }),
      });
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
    error.textContent = err.message;
  }
  pintar();
});

api("/api/info").then(i => {
  document.getElementById("demanda").hidden = !["real", "plan", "ensayo"].includes(i.infra);
}).catch(() => {});

function arrancar() {
  if (!usuario || !token) return;
  document.getElementById("ingreso").hidden = true;
  document.getElementById("panel").hidden = false;
  pintar();
  setInterval(() => pintar().catch(() => {}), 3000);
}
arrancar();
