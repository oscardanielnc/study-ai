const $ = (sel) => document.querySelector(sel);
const app = () => $("#app");
const NIVELES = [
  ["facil", "Fácil"],
  ["intermedio", "Intermedio"],
  ["dificil", "Difícil"],
];
const CANTIDADES = [10, 20, 30, 40];

async function api(ruta, opciones = {}) {
  const r = await fetch(`/api${ruta}`, opciones);
  if (!r.ok) {
    const cuerpo = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(cuerpo.detail || `Error ${r.status}`);
  }
  return r.status === 204 ? null : r.json();
}

function pintar(html, conBarra = false) {
  app().className = conBarra ? "con-barra" : "";
  app().innerHTML = html;
}

function fallo(mensaje, volver) {
  pintar(`<p class="error">${mensaje}</p>
    <button class="secundario" onclick="${volver}">← Volver</button>`);
}

async function pintarGasto() {
  try {
    const g = await api("/gasto");
    $("#gasto").textContent = `$${g.mes_usd.toFixed(3)} / $${g.tope_usd}`;
  } catch {
    $("#gasto").textContent = "";
  }
}

/** El modelo alterna entre $...$ y \(...\) para las formulas. Hay que pasarlo
 *  todo a $ ANTES de marked: marked lee \( como un escape de markdown y deja
 *  el parentesis pelado, asi que KaTeX no llegaria a ver nunca la formula. */
function normalizarFormulas(md) {
  const BS = String.fromCharCode(92);
  return md
    .split(BS + "[").join("$$")
    .split(BS + "]").join("$$")
    .split(BS + "(").join("$")
    .split(BS + ")").join("$");
}

function renderizar(el) {
  renderMathInElement(el, {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "$", right: "$", display: false },
    ],
    throwOnError: false,
  });
}

// ---------- Lista de temas ----------

async function vistaTemas() {
  location.hash = "";
  const temas = await api("/temas");
  pintar(`
    <button onclick="nuevoTema()">+ Nuevo tema</button>
    <input type="file" id="archivos" multiple accept="image/*,.pdf" hidden>
    ${
      temas.length === 0
        ? `<p class="vacio">Aún no tienes temas.<br>Sube fotos de tus apuntes para empezar.</p>`
        : temas
            .map(
              (t) => `
      <div class="tarjeta" onclick="vistaTema(${t.id})">
        <h3>${t.titulo}</h3>
        <small>${t.n_fuentes} archivo${t.n_fuentes === 1 ? "" : "s"} · ${
                t.actualizado_en
              }</small>
      </div>`
            )
            .join("")
    }`);
  pintarGasto();
}

function nuevoTema() {
  const input = $("#archivos");
  input.onchange = async () => {
    if (!input.files.length) return;
    const fd = new FormData();
    for (const f of input.files) fd.append("archivos", f);
    try {
      const { tema_id, job_id } = await api("/temas", { method: "POST", body: fd });
      seguirJob(job_id, "Procesando tus apuntes…", () => vistaTema(tema_id));
    } catch (e) {
      fallo(e.message, "vistaTemas()");
    }
  };
  input.click();
}

/** Sondea un job hasta que termina. El tunel corta las peticiones a los 100 s:
 *  nunca esperamos dentro de la misma peticion HTTP. */
function seguirJob(jobId, titulo, alTerminar, alFallar) {
  pintar(`<p>${titulo}</p>
    <div class="progreso"><div id="pb" style="width:0%"></div></div>
    <p id="pt" class="marcador"></p>`);
  const tic = async () => {
    const j = await api(`/jobs/${jobId}`);
    const pct = j.progreso_total ? (j.progreso_actual / j.progreso_total) * 100 : 0;
    $("#pb").style.width = `${pct}%`;
    $("#pt").textContent = `${j.progreso_actual} / ${j.progreso_total}`;
    if (j.estado === "completado") return alTerminar();
    if (j.estado === "fallido") {
      pintar(`<p class="error">Falló: ${j.error}</p>`);
      return alFallar ? alFallar() : null;
    }
    setTimeout(tic, 2000);
  };
  tic();
}

// ---------- Vista de un tema ----------

/** El modelo describe con [DIAGRAMA: ...] lo que no pudo reproducir. Se marca
 *  aparte para que no se confunda con contenido realmente transcrito. */
function marcarDiagramas(html) {
  return html.replace(
    /<p>\s*\[?DIAGRAMA:([^\]<]*)\]?\s*<\/p>/gi,
    '<div class="diagrama">$1</div>'
  );
}

async function vistaTema(id) {
  location.hash = `tema-${id}`;
  let t, hist;
  try {
    [t, hist] = await Promise.all([api(`/temas/${id}`), api(`/temas/${id}/examenes`)]);
  } catch (e) {
    return fallo(e.message, "vistaTemas()");
  }

  pintar(
    `
    <button class="volver" onclick="vistaTemas()">← Temas</button>
    <div id="resumen"></div>
    ${
      hist.length
        ? `<div class="historial"><h2>Historial</h2>${hist
            .map(
              (e) => `<div class="fila">
                <span>${e.nivel}</span>
                <span class="puntaje">${e.aciertos}/${e.total}</span>
              </div>`
            )
            .join("")}</div>`
        : ""
    }
    <div class="barra">
      <button class="principal" onclick="configurarExamen(${id})">Tomar examen</button>
      <button class="secundario" onclick="anadirMaterial(${id})">Añadir material</button>
    </div>
    <input type="file" id="mas" multiple accept="image/*,.pdf" hidden>`,
    true
  );

  const destino = $("#resumen");
  destino.innerHTML = marcarDiagramas(
    marked.parse(normalizarFormulas(t.resumen_md || "_Sin resumen._"))
  );
  // Las tablas anchas scrollean dentro de su caja; la pagina nunca se mueve
  // en horizontal.
  destino.querySelectorAll("table").forEach((tabla) => {
    const caja = document.createElement("div");
    caja.className = "tabla-scroll";
    tabla.replaceWith(caja);
    caja.appendChild(tabla);
  });
  renderizar(destino);
  pintarGasto();
}

function anadirMaterial(temaId) {
  const input = $("#mas");
  input.onchange = async () => {
    if (!input.files.length) return;
    const fd = new FormData();
    for (const f of input.files) fd.append("archivos", f);
    try {
      const { job_id } = await api(`/temas/${temaId}/material`, {
        method: "POST",
        body: fd,
      });
      seguirJob(job_id, "Procesando el material nuevo…", () => vistaTema(temaId));
    } catch (e) {
      fallo(e.message, `vistaTema(${temaId})`);
    }
  };
  input.click();
}

// ---------- Configurar examen ----------

const elegido = { nivel: "intermedio", cantidad: 10 };

function configurarExamen(temaId) {
  const botones = (items, campo) =>
    items
      .map(
        ([valor, texto]) =>
          `<button class="elegible" data-campo="${campo}" data-valor="${valor}"
             aria-pressed="${elegido[campo] == valor}">${texto}</button>`
      )
      .join("");

  pintar(
    `
    <button class="volver" onclick="vistaTema(${temaId})">← Volver</button>
    <h1>Configurar examen</h1>
    <div class="grupo">
      <h2>Nivel de dificultad</h2>
      <div class="opciones-nivel">${botones(NIVELES, "nivel")}</div>
    </div>
    <div class="grupo">
      <h2>Cantidad de preguntas</h2>
      <div class="cantidades">${botones(
        CANTIDADES.map((n) => [n, n]),
        "cantidad"
      )}</div>
    </div>
    <p class="aviso" id="aviso"></p>
    <div class="barra">
      <button class="principal" onclick="iniciarExamen(${temaId})">Iniciar examen</button>
    </div>`,
    true
  );

  const refrescarAviso = () => {
    // Cota superior: si ya hay preguntas sin ver, no se genera nada.
    const seg = Math.round((elegido.cantidad * 12) / 10) * 10;
    $("#aviso").textContent = `Si hay que generarlas, tarda hasta ~${seg} s.`;
  };
  document.querySelectorAll(".elegible").forEach((b) => {
    b.onclick = () => {
      const campo = b.dataset.campo;
      elegido[campo] = campo === "cantidad" ? Number(b.dataset.valor) : b.dataset.valor;
      document
        .querySelectorAll(`.elegible[data-campo="${campo}"]`)
        .forEach((o) => o.setAttribute("aria-pressed", o === b));
      refrescarAviso();
    };
  });
  refrescarAviso();
}

async function iniciarExamen(temaId) {
  const peticion = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(elegido),
  };
  let r;
  try {
    r = await api(`/temas/${temaId}/examenes`, peticion);
  } catch (e) {
    return fallo(e.message, `vistaTema(${temaId})`);
  }

  if (r.examen_id) return vistaExamen(temaId, r);

  const plural = r.faltan === 1 ? "" : "s";
  seguirJob(
    r.job_id,
    `Preparando ${r.faltan} pregunta${plural} nueva${plural}…`,
    async () => {
      try {
        vistaExamen(temaId, await api(`/temas/${temaId}/examenes`, peticion));
      } catch (e) {
        fallo(e.message, `vistaTema(${temaId})`);
      }
    }
  );
}

// ---------- Examen ----------

function vistaExamen(temaId, ex) {
  let i = 0;
  let aciertos = 0;
  const total = ex.preguntas.length;

  const pregunta = () => {
    const p = ex.preguntas[i];
    pintar(`
      <div class="marcador">
        <span>Pregunta ${i + 1}/${total}</span>
        <span><span class="aciertos">✓ ${aciertos}</span>
          &nbsp;<span class="fallos">✕ ${i - aciertos}</span></span>
      </div>
      <div class="progreso"><div style="width:${(i / total) * 100}%"></div></div>
      <div class="enunciado">${p.enunciado}</div>
      <div id="opciones">${p.opciones
        .map(
          (o, k) =>
            `<button class="opcion" data-k="${k}"><span>${o}</span>
               <span class="marca"></span></button>`
        )
        .join("")}</div>
      <div id="feedback"></div>`);
    renderizar(app());
    document.querySelectorAll(".opcion").forEach((b) => {
      b.onclick = () => marcar(p, Number(b.dataset.k));
    });
  };

  const marcar = async (p, k) => {
    const opciones = [...document.querySelectorAll(".opcion")];
    opciones.forEach((b) => (b.disabled = true));
    let r;
    try {
      r = await api(`/examenes/${ex.examen_id}/respuestas`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pregunta_id: p.id, elegida_idx: k }),
      });
    } catch (e) {
      return fallo(e.message, `vistaTema(${temaId})`);
    }
    if (r.correcta) aciertos++;

    // El acierto y el fallo nunca dependen solo del color: llevan icono propio.
    opciones.forEach((b) => {
      const n = Number(b.dataset.k);
      if (n === r.correcta_idx) {
        b.classList.add("buena");
        b.querySelector(".marca").textContent = "✓";
      } else if (n === k) {
        b.classList.add("mala");
        b.querySelector(".marca").textContent = "✕";
      } else {
        b.classList.add("apagada");
      }
    });

    const fb = $("#feedback");
    fb.innerHTML = `<div class="porque"><h4>Por qué</h4>${r.justificacion}</div>
      <button id="sig">${i + 1 < total ? "Siguiente" : "Ver resultado"}</button>`;
    renderizar(fb);
    $("#sig").onclick = () => {
      i++;
      i < total ? pregunta() : terminar();
    };
  };

  const terminar = async () => {
    const r = await api(`/examenes/${ex.examen_id}/finalizar`, { method: "POST" });
    pintar(`
      <div class="resultado">
        <div class="nota">${r.aciertos}/${r.total}</div>
        <div class="de">${Math.round((r.aciertos / r.total) * 100)}% de aciertos</div>
      </div>
      <button onclick="configurarExamen(${temaId})">Otro examen</button>
      <button class="secundario" onclick="vistaTema(${temaId})">← Volver al tema</button>`);
    pintarGasto();
  };

  pregunta();
}

window.addEventListener("DOMContentLoaded", () => {
  const m = location.hash.match(/^#tema-(\d+)$/);
  m ? vistaTema(Number(m[1])) : vistaTemas();
});
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
