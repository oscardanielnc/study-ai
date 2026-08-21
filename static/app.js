const $ = (sel) => document.querySelector(sel);
const app = () => $("#app");
const ICONO_NIVEL = { facil: "🟢", intermedio: "🟡", dificil: "🔴" };

async function api(ruta, opciones = {}) {
  const r = await fetch(`/api${ruta}`, opciones);
  if (!r.ok) {
    const cuerpo = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(cuerpo.detail || `Error ${r.status}`);
  }
  return r.status === 204 ? null : r.json();
}

async function pintarGasto() {
  try {
    const g = await api("/gasto");
    $("#gasto").textContent = `$${g.mes_usd.toFixed(3)} / $${g.tope_usd}`;
  } catch {
    $("#gasto").textContent = "";
  }
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
  app().innerHTML = `
    <button onclick="nuevoTema()">+ Nuevo tema</button>
    <input type="file" id="archivos" multiple accept="image/*,.pdf" hidden>
    ${temas.length === 0 ? "<p>Aún no tienes temas. Sube tus apuntes.</p>" : ""}
    ${temas
      .map(
        (t) => `
      <div class="tarjeta" onclick="vistaTema(${t.id})">
        <h3>${t.titulo}</h3>
        <small>${t.n_fuentes} archivo(s) · ${t.actualizado_en}</small>
      </div>`
      )
      .join("")}`;
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
      seguirJob(job_id, tema_id);
    } catch (e) {
      app().innerHTML = `<p class="error">${e.message}</p>
        <button class="secundario" onclick="vistaTemas()">← Volver</button>`;
    }
  };
  input.click();
}

async function seguirJob(jobId, temaId) {
  app().innerHTML = `<p>Procesando tus apuntes…</p>
    <div class="barra"><div id="pb" style="width:0%"></div></div>
    <p id="pt" class="marcador"></p>`;
  const tic = async () => {
    const j = await api(`/jobs/${jobId}`);
    const pct = j.progreso_total ? (j.progreso_actual / j.progreso_total) * 100 : 0;
    $("#pb").style.width = `${pct}%`;
    $("#pt").textContent = `${j.progreso_actual} / ${j.progreso_total}`;
    if (j.estado === "completado") return vistaTema(temaId);
    if (j.estado === "fallido") {
      app().innerHTML = `<p class="error">Falló: ${j.error}</p>
        <button class="secundario" onclick="vistaTema(${temaId})">Ver tema igual</button>
        <button class="secundario" onclick="vistaTemas()">← Temas</button>`;
      return;
    }
    setTimeout(tic, 2000);
  };
  tic();
}

// ---------- Vista de un tema ----------

async function vistaTema(id) {
  location.hash = `tema-${id}`;
  const [t, hist] = await Promise.all([
    api(`/temas/${id}`),
    api(`/temas/${id}/examenes`),
  ]);
  app().innerHTML = `
    <button class="secundario" onclick="vistaTemas()">← Temas</button>
    <div id="resumen"></div>
    <button onclick="elegirNivel(${id})">📝 Tomar examen</button>
    <button class="secundario" onclick="anadirMaterial(${id})">+ Añadir material</button>
    <input type="file" id="mas" multiple accept="image/*,.pdf" hidden>
    ${
      hist.length
        ? `<h2>Historial</h2>${hist
            .map(
              (e) => `<div class="marcador">${ICONO_NIVEL[e.nivel]} ${e.nivel} ·
                ${e.aciertos}/${e.total} · ${e.terminado_en}</div>`
            )
            .join("")}`
        : ""
    }`;
  const destino = $("#resumen");
  destino.innerHTML = marked.parse(t.resumen_md || "_Sin resumen._");
  renderizar(destino);
}

function anadirMaterial(temaId) {
  const input = $("#mas");
  input.onchange = async () => {
    if (!input.files.length) return;
    const fd = new FormData();
    for (const f of input.files) fd.append("archivos", f);
    const { job_id } = await api(`/temas/${temaId}/material`, {
      method: "POST",
      body: fd,
    });
    seguirJob(job_id, temaId);
  };
  input.click();
}

function elegirNivel(temaId) {
  app().innerHTML = `
    <button class="secundario" onclick="vistaTema(${temaId})">← Volver</button>
    <h2>Dificultad</h2>
    <button onclick="vistaExamen(${temaId}, 'facil')">🟢 Fácil</button>
    <button onclick="vistaExamen(${temaId}, 'intermedio')">🟡 Intermedio</button>
    <button onclick="vistaExamen(${temaId}, 'dificil')">🔴 Difícil</button>
    <p class="marcador">¿Ya te sabes las preguntas? Genera 20 nuevas:</p>
    <button class="secundario" onclick="generarMas(${temaId}, 'facil')">+20 fáciles</button>
    <button class="secundario" onclick="generarMas(${temaId}, 'intermedio')">+20 intermedias</button>
    <button class="secundario" onclick="generarMas(${temaId}, 'dificil')">+20 difíciles</button>`;
}

async function generarMas(temaId, nivel) {
  app().innerHTML = "<p>Generando preguntas nuevas…</p>";
  try {
    const { generadas } = await api(`/temas/${temaId}/preguntas`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nivel }),
    });
    app().innerHTML = `<p>✅ ${generadas} preguntas añadidas al nivel ${nivel}.</p>
      <button onclick="vistaExamen(${temaId}, '${nivel}')">Tomar examen</button>
      <button class="secundario" onclick="vistaTema(${temaId})">← Volver</button>`;
  } catch (e) {
    app().innerHTML = `<p class="error">${e.message}</p>
      <button class="secundario" onclick="vistaTema(${temaId})">← Volver</button>`;
  }
  pintarGasto();
}

// ---------- Examen ----------

async function vistaExamen(temaId, nivel) {
  app().innerHTML = "<p>Preparando el examen…</p>";
  let ex;
  try {
    ex = await api(`/temas/${temaId}/examenes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nivel }),
    });
  } catch (e) {
    app().innerHTML = `<p class="error">${e.message}</p>
      <button class="secundario" onclick="vistaTema(${temaId})">← Volver</button>`;
    return;
  }

  let i = 0;
  let aciertos = 0;
  const total = ex.preguntas.length;

  const pintar = () => {
    const p = ex.preguntas[i];
    app().innerHTML = `
      <div class="marcador">Pregunta ${i + 1}/${total} · ✅ ${aciertos} · ❌ ${
      i - aciertos
    }</div>
      <div class="barra"><div style="width:${(i / total) * 100}%"></div></div>
      <h3 id="enunciado">${p.enunciado}</h3>
      <div id="opciones">${p.opciones
        .map((o, k) => `<button class="opcion" data-k="${k}">${o}</button>`)
        .join("")}</div>
      <div id="feedback"></div>`;
    renderizar(app());
    document.querySelectorAll(".opcion").forEach((b) => {
      b.onclick = () => marcar(p, Number(b.dataset.k));
    });
  };

  const marcar = async (p, k) => {
    document.querySelectorAll(".opcion").forEach((b) => (b.disabled = true));
    const r = await api(`/examenes/${ex.examen_id}/respuestas`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pregunta_id: p.id, elegida_idx: k }),
    });
    if (r.correcta) aciertos++;
    document
      .querySelector(`.opcion[data-k="${r.correcta_idx}"]`)
      .classList.add("correcta");
    if (!r.correcta) {
      document.querySelector(`.opcion[data-k="${k}"]`).classList.add("incorrecta");
    }
    const fb = $("#feedback");
    fb.innerHTML = `<div class="justificacion">${r.justificacion}</div>
      <button id="sig">${i + 1 < total ? "Siguiente →" : "Ver resultado"}</button>`;
    renderizar(fb);
    $("#sig").onclick = () => {
      i++;
      i < total ? pintar() : terminar();
    };
  };

  const terminar = async () => {
    const r = await api(`/examenes/${ex.examen_id}/finalizar`, { method: "POST" });
    const pct = Math.round((r.aciertos / r.total) * 100);
    app().innerHTML = `
      <h2>${pct >= 70 ? "🎉" : "📚"} ${r.aciertos} / ${r.total} (${pct}%)</h2>
      <button onclick="vistaExamen(${temaId}, '${nivel}')">Repetir nivel</button>
      <button class="secundario" onclick="vistaTema(${temaId})">← Volver al tema</button>`;
    pintarGasto();
  };

  pintar();
}

window.addEventListener("DOMContentLoaded", () => {
  const m = location.hash.match(/^#tema-(\d+)$/);
  m ? vistaTema(Number(m[1])) : vistaTemas();
});
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
