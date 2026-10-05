// Gráficos SVG mínimos: líneas con línea guía y barras apiladas al 100 %.
// Los colores salen de los tokens --serie-N de estilo.css, validados para ambos modos.
// Las etiquetas pueden venir de datos: siempre por textContent, nunca por innerHTML.

const SVG = "http://www.w3.org/2000/svg";

function el(tag, attrs = {}, parent) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}

function tooltip(contenedor) {
  let t = contenedor.querySelector(".tip");
  if (!t) {
    t = document.createElement("div");
    t.className = "tip";
    t.hidden = true;
    contenedor.appendChild(t);
  }
  return t;
}

function filasTip(t, titulo, filas) {
  t.replaceChildren();
  const h = document.createElement("div");
  h.className = "tip-titulo";
  h.textContent = titulo;
  t.appendChild(h);
  for (const f of filas) {
    const fila = document.createElement("div");
    fila.className = "tip-fila";
    const clave = document.createElement("span");
    clave.className = "tip-clave";
    clave.style.background = f.color;
    const valor = document.createElement("strong");
    valor.textContent = f.valor;
    const nombre = document.createElement("span");
    nombre.className = "tenue";
    nombre.textContent = f.nombre;
    fila.append(clave, valor, nombre);
    t.appendChild(fila);
  }
}

function leyenda(contenedor, series, forma = "linea") {
  const l = document.createElement("div");
  l.className = "leyenda";
  for (const s of series) {
    const item = document.createElement("span");
    const marca = document.createElement("span");
    marca.className = forma === "linea" ? "ley-linea" : "ley-caja";
    marca.style.background = s.color;
    const texto = document.createElement("span");
    texto.textContent = s.nombre;
    item.append(marca, texto);
    l.appendChild(item);
  }
  contenedor.appendChild(l);
}

// series: [{nombre, valores: [num|null], color}], x: [etiquetas]
function lineas(contenedor, { x, series, formato = v => v.toFixed(2), titulo = i => `tick ${x[i]}` }) {
  const previo = contenedor._hover;
  contenedor.replaceChildren();
  contenedor.classList.add("grafico");
  leyenda(contenedor, series);
  const W = 640, H = 200, M = { t: 10, r: 104, b: 22, l: 40 };
  const todos = series.flatMap(s => s.valores).filter(v => v != null);
  if (todos.length < 2) {
    const vacio = document.createElement("p");
    vacio.className = "tenue pequeno";
    vacio.textContent = "Todavía no hay datos. Inicia la simulación.";
    contenedor.appendChild(vacio);
    return;
  }
  let min = Math.min(0, ...todos), max = Math.max(...todos) * 1.08 || 1;
  const sx = i => M.l + (i / Math.max(1, x.length - 1)) * (W - M.l - M.r);
  const sy = v => M.t + (1 - (v - min) / (max - min)) * (H - M.t - M.b);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", class: "lienzo" }, contenedor);
  for (let k = 0; k <= 3; k++) {
    const v = min + (k / 3) * (max - min);
    el("line", { x1: M.l, x2: W - M.r, y1: sy(v), y2: sy(v), class: "rejilla" }, svg);
    const t = el("text", { x: M.l - 6, y: sy(v) + 4, "text-anchor": "end", class: "eje" }, svg);
    t.textContent = formato(v);
  }
  const etiquetas = [];
  for (const s of series) {
    let d = "", abierto = false;
    s.valores.forEach((v, i) => {
      if (v == null) { abierto = false; return; }
      d += `${abierto ? "L" : "M"}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`;
      abierto = true;
    });
    el("path", { d, class: "serie", style: `stroke:${s.color}` }, svg);
    // Etiqueta directa al final de la línea.
    const ult = s.valores.map((v, i) => [v, i]).filter(([v]) => v != null).pop();
    if (ult) etiquetas.push({ nombre: s.nombre, x: sx(ult[1]) + 6, y: sy(ult[0]) + 4 });
  }
  // Etiquetas directas sin encimarse: de arriba abajo, al menos 13 px entre una y otra.
  etiquetas.sort((a, b) => a.y - b.y);
  etiquetas.forEach((e, i) => {
    if (i && e.y - etiquetas[i - 1].y < 13) e.y = etiquetas[i - 1].y + 13;
    el("text", { x: e.x, y: e.y, class: "eje etiqueta" }, svg).textContent = e.nombre;
  });
  const guia = el("line", { y1: M.t, y2: H - M.b, class: "guia", visibility: "hidden" }, svg);
  const tip = tooltip(contenedor);
  const mostrar = i => {
    contenedor._hover = i;
    guia.setAttribute("x1", sx(i));
    guia.setAttribute("x2", sx(i));
    guia.setAttribute("visibility", "visible");
    filasTip(tip, titulo(i), series.map(s => ({
      nombre: s.nombre, color: s.color, valor: s.valores[i] == null ? "—" : formato(s.valores[i]),
    })));
    tip.hidden = false;
    tip.style.left = `${Math.min(70, (sx(i) / W) * 100)}%`;
  };
  const ocultar = () => {
    contenedor._hover = null;
    guia.setAttribute("visibility", "hidden");
    tip.hidden = true;
  };
  const hit = el("rect", { x: M.l, y: 0, width: W - M.l - M.r, height: H, fill: "transparent", tabindex: 0 }, svg);
  hit.addEventListener("pointermove", e => {
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    mostrar(Math.max(0, Math.min(x.length - 1, Math.round(((px - M.l) / (W - M.l - M.r)) * (x.length - 1)))));
  });
  hit.addEventListener("focus", () => mostrar(x.length - 1));
  hit.addEventListener("pointerleave", ocultar);
  hit.addEventListener("blur", ocultar);
  if (previo != null && previo < x.length) mostrar(previo);
}

// categorias: ["g1", ...]; series: [{nombre, valores: [0..1], color}]
function apiladas(contenedor, { categorias, series, titulo = c => c }) {
  contenedor.replaceChildren();
  contenedor.classList.add("grafico");
  leyenda(contenedor, series, "caja");
  if (!categorias.length) {
    const vacio = document.createElement("p");
    vacio.className = "tenue pequeno";
    vacio.textContent = "Aún no cierra ninguna generación.";
    contenedor.appendChild(vacio);
    return;
  }
  const W = 640, H = 180, M = { t: 6, r: 8, b: 22, l: 8 }, GAP = 2;
  const ancho = (W - M.l - M.r) / categorias.length;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", class: "lienzo" }, contenedor);
  const tip = tooltip(contenedor);
  categorias.forEach((c, i) => {
    const x = M.l + i * ancho + GAP;
    const w = Math.max(2, ancho - GAP * 2);
    let base = H - M.b;
    series.forEach(s => {
      const h = s.valores[i] * (H - M.t - M.b);
      if (h <= 0) return;
      const r = el("rect", {
        x, y: base - h + GAP / 2, width: w, height: Math.max(0, h - GAP), rx: 2,
        style: `fill:${s.color}`, class: "segmento", tabindex: 0,
      }, svg);
      const mostrar = () => {
        filasTip(tip, titulo(c), series.map(o => ({
          nombre: o.nombre, color: o.color, valor: `${Math.round(o.valores[i] * 100)} %`,
        })));
        tip.hidden = false;
        tip.style.left = `${Math.min(70, (x / W) * 100)}%`;
      };
      r.addEventListener("pointermove", mostrar);
      r.addEventListener("focus", mostrar);
      r.addEventListener("pointerleave", () => { tip.hidden = true; });
      r.addEventListener("blur", () => { tip.hidden = true; });
      base -= h;
    });
    const t = el("text", { x: x + w / 2, y: H - 6, "text-anchor": "middle", class: "eje" }, svg);
    t.textContent = c;
  });
}
