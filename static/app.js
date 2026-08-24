const $ = (sel) => document.querySelector(sel);
const app = () => $("#app");
const NIVELES = [
  ["facil", "Fácil"],
  ["intermedio", "Intermedio"],
  ["dificil", "Difícil"],
];
const CANTIDADES = [10, 20, 30, 40];

// Sondeo del job en curso. Vive arriba porque `pintar` lo cancela.
let sondear = null;
let temporizador = null;
let latido = null;

/** Lo que hace el servidor mientras la barra no se mueve. Con 10 preguntas es
 *  una sola llamada al modelo: tres minutos clavado en "0 / 10" parecian un
 *  cuelgue. Aqui no se inventa progreso, se cuenta lo que esta pasando. */
const FRASES = {
  transcribir: [
    "Leyendo tus archivos…",
    "Transcribiendo la escritura…",
    "Interpretando diagramas y fórmulas…",
    "Ordenando los conceptos…",
    "Redactando el resumen…",
    "Puliendo la redacción…",
  ],
  generar_preguntas: [
    "Repasando tus apuntes…",
    "Buscando lo evaluable…",
    "Pensando…",
    "Redactando los enunciados…",
    "Inventando opciones creíbles…",
    "Revisando las respuestas correctas…",
  ],
};

async function api(ruta, opciones = {}) {
  const r = await fetch(`/api${ruta}`, opciones);
  if (!r.ok) {
    const cuerpo = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(cuerpo.detail || `Error ${r.status}`);
  }
  return r.status === 204 ? null : r.json();
}

function pintar(html, conBarra = false) {
  // Cambiar de pantalla cancela el sondeo anterior: si no, dos jobs solapados
  // se pisarian la barra de progreso.
  clearTimeout(temporizador);
  clearInterval(latido);
  sondear = null;
  app().className = conBarra ? "con-barra" : "";
  app().innerHTML = html;
}

/** Pantalla de espera con barra. Se pinta en cuanto hay algo que esperar: el
 *  usuario nunca debe quedarse mirando una pantalla quieta. */
function cargando(titulo, detalle = "", frases = null) {
  pintar(`<p class="cargando">${titulo}</p>
    <div class="progreso indeterminada"><div id="pb" style="width:0%"></div></div>
    <p id="pt" class="marcador">${detalle}</p>
    ${frases ? '<p id="frase" class="susurro"></p>' : ""}`);
  if (!frases) return;

  // El reloj se mueve cada segundo y la frase cada cinco. Ninguno adivina
  // cuanto falta: solo demuestran que la app sigue viva.
  const desde = Date.now();
  const paso = () => {
    const seg = Math.floor((Date.now() - desde) / 1000);
    const reloj = `${Math.floor(seg / 60)}:${String(seg % 60).padStart(2, "0")}`;
    const frase = frases[Math.floor(seg / 5) % frases.length];
    $("#frase").innerHTML = `${frase} <span class="reloj">${reloj}</span>`;
  };
  paso();
  latido = setInterval(paso, 1000);
}

function avanzar(fraccion, detalle = "") {
  const pb = $("#pb");
  if (!pb) return;
  // En cuanto hay progreso real, la barra deja de ser un vaiven y mide.
  if (fraccion > 0) pb.parentElement.classList.remove("indeterminada");
  pb.style.width = `${Math.round(fraccion * 100)}%`;
  $("#pt").textContent = detalle;
}

/** Confirmacion propia: `confirm()` del navegador congela la app dentro del
 *  APK y se ve como un aviso del sistema, no como parte de Estudia. */
function confirmar(html, alSi) {
  const fondo = document.createElement("div");
  fondo.className = "modal";
  fondo.innerHTML = `<div class="hoja">
      <div class="dice">${html}</div>
      <button class="peligro" id="si">Eliminar</button>
      <button class="secundario" id="no">Cancelar</button>
    </div>`;
  document.body.appendChild(fondo);
  const cerrar = () => fondo.remove();
  fondo.onclick = (e) => e.target === fondo && cerrar();
  fondo.querySelector("#no").onclick = cerrar;
  fondo.querySelector("#si").onclick = () => {
    cerrar();
    alSi();
  };
}

function fallo(mensaje, volver) {
  pintar(`<p class="error">${mensaje}</p>
    <button class="secundario" onclick="${volver}">← Volver</button>`);
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
    <button class="nuevo" onclick="nuevoTema()">+ Nuevo tema</button>
    <input type="file" id="archivos" multiple accept="image/*,.pdf" hidden>
    ${
      temas.length === 0
        ? `<p class="vacio">Aún no tienes temas.<br>Sube fotos de tus apuntes para empezar.</p>`
        : temas
            .map(
              (t) => `
      <div class="tarjeta" data-id="${t.id}" onclick="vistaTema(${t.id})">
        <div class="cuerpo">
          <h3>${t.titulo}</h3>
          <small>${t.n_fuentes} archivo${t.n_fuentes === 1 ? "" : "s"} · ${
                t.actualizado_en
              }</small>
        </div>
        <button class="borrar" aria-label="Eliminar tema"
          onclick="event.stopPropagation(); pedirBorrar(${t.id})">✕</button>
      </div>`
            )
            .join("")
    }`);
}

/** Borrar es irreversible y la papelera esta pegada a la tarjeta: siempre
 *  se pregunta, y se dice exactamente que se lleva por delante. */
function pedirBorrar(id) {
  const titulo = $(`.tarjeta[data-id="${id}"] h3`).textContent;
  confirmar(
    `¿Eliminar <b>${titulo}</b>?<br>
     <small>Se borran su resumen, sus preguntas y su historial de exámenes.
     No se puede deshacer.</small>`,
    async () => {
      try {
        await api(`/temas/${id}`, { method: "DELETE" });
      } catch (e) {
        return fallo(e.message, "vistaTemas()");
      }
      vistaTemas();
    }
  );
}

// ---------- Subida ----------

/** El servidor reduce las imagenes a 1100 px de todos modos, asi que bajarlas
 *  aqui no cuesta calidad util: una foto de 12 MP pasa de ~4 MB a ~250 KB y la
 *  subida, de un minuto a unos segundos. Menos tiempo en el que apagar la
 *  pantalla pueda cortarla, que es lo unico que aun no vive en el servidor. */
const LADO_MAX = 1600;

function comprimir(archivo) {
  if (!archivo.type.startsWith("image/")) return Promise.resolve(archivo);
  return new Promise((resolve) => {
    const img = new Image();
    const url = URL.createObjectURL(archivo);
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(archivo); // formato que el movil no sabe pintar: decide el servidor
    };
    img.onload = () => {
      const escala = Math.min(1, LADO_MAX / Math.max(img.width, img.height));
      const lienzo = document.createElement("canvas");
      lienzo.width = Math.round(img.width * escala);
      lienzo.height = Math.round(img.height * escala);
      lienzo.getContext("2d").drawImage(img, 0, 0, lienzo.width, lienzo.height);
      URL.revokeObjectURL(url);
      lienzo.toBlob(
        (b) =>
          resolve(
            b && b.size < archivo.size
              ? new File([b], archivo.name, { type: "image/jpeg" })
              : archivo
          ),
        "image/jpeg",
        0.85
      );
    };
    img.src = url;
  });
}

/** fetch no informa del progreso de subida, y aqui importa: son los segundos en
 *  los que el usuario no sabe si esta pasando algo. XHR si lo da. */
function subir(ruta, archivos, alProgreso) {
  return new Promise((resolve, rechazar) => {
    const fd = new FormData();
    for (const f of archivos) fd.append("archivos", f);
    const x = new XMLHttpRequest();
    x.open("POST", `/api${ruta}`);
    x.upload.onprogress = (e) =>
      e.lengthComputable && alProgreso(e.loaded / e.total);
    x.onload = () => {
      let cuerpo = {};
      try {
        cuerpo = JSON.parse(x.responseText);
      } catch {}
      if (x.status >= 200 && x.status < 300) return resolve(cuerpo);
      rechazar(new Error(cuerpo.detail || `Error ${x.status}`));
    };
    x.onerror = () =>
      rechazar(new Error("Se cortó la conexión al subir. Inténtalo otra vez."));
    x.send(fd);
  });
}

function nuevoTema() {
  const input = $("#archivos");
  input.onchange = async () => {
    const archivos = [...input.files];
    input.value = ""; // permite reintentar con los mismos archivos
    if (!archivos.length) return;

    // Respuesta inmediata: preparar las fotos ya tarda sus segundos y hasta
    // ahora ese hueco se veia como si la app no hubiera hecho nada.
    cargando("Preparando tus archivos…", `0 / ${archivos.length}`);
    try {
      const listos = [];
      for (const f of archivos) {
        listos.push(await comprimir(f));
        avanzar(
          listos.length / archivos.length,
          `${listos.length} / ${archivos.length}`
        );
      }
      cargando("Subiendo…");
      const { tema_id, job_id } = await subir("/temas", listos, (r) =>
        avanzar(r, `${Math.round(r * 100)}%`)
      );
      // El hash entra ya: si el movil descarta la pestana, al volver se
      // reengancha al proceso en vez de perderlo.
      location.hash = `tema-${tema_id}`;
      seguirJob(job_id, "transcribir", "Procesando tus apuntes…", () =>
        vistaTema(tema_id)
      );
    } catch (e) {
      fallo(e.message, "vistaTemas()");
    }
  };
  input.click();
}

/** El trabajo ocurre entero en el servidor; esto solo mira. Por eso apagar la
 *  pantalla, cambiar de pestana o recargar ya no lo interrumpe: como mucho se
 *  deja de mirar un rato. Un fallo de red suelto tampoco lo mata: se insiste. */
const REINTENTOS = 60; // ~5 min de red caida antes de rendirse

function seguirJob(jobId, tipo, titulo, alTerminar, alFallar) {
  cargando(titulo, "", FRASES[tipo]);
  let fallos = 0;
  const tic = async () => {
    clearTimeout(temporizador);
    if (sondear !== tic) return; // ya se cambio de pantalla
    let j;
    try {
      j = await api(`/jobs/${jobId}`);
      fallos = 0;
    } catch {
      if (++fallos > REINTENTOS) {
        return fallo(
          "Sin conexión con el servidor. El proceso sigue en marcha:" +
            " vuelve a entrar al tema dentro de un momento.",
          "vistaTemas()"
        );
      }
      temporizador = setTimeout(tic, 5000);
      return;
    }
    avanzar(
      j.progreso_total ? j.progreso_actual / j.progreso_total : 0,
      `${j.progreso_actual} / ${j.progreso_total}`
    );
    if (j.estado === "completado") return alTerminar();
    if (j.estado === "fallido") {
      pintar(`<p class="error">Falló: ${j.error}</p>
        <button class="secundario" onclick="vistaTemas()">← Volver</button>`);
      return alFallar ? alFallar() : null;
    }
    temporizador = setTimeout(tic, 2000);
  };
  sondear = tic;
  tic();
}

// Al volver de la pantalla apagada el temporizador puede llevar minutos parado:
// se sondea al instante en vez de esperar al siguiente turno.
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && sondear) sondear();
});

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
  let t, hist, job;
  try {
    [t, hist, job] = await Promise.all([
      api(`/temas/${id}`),
      api(`/temas/${id}/examenes`),
      api(`/temas/${id}/job`),
    ]);
  } catch (e) {
    return fallo(e.message, "vistaTemas()");
  }

  // Reenganche: si el tema sigue procesandose (recarga, pestana descartada,
  // movil dormido) se vuelve a la barra en vez de mostrar un resumen vacio.
  if (job && (job.estado === "pendiente" || job.estado === "en_curso")) {
    return seguirJob(
      job.id,
      job.tipo,
      job.tipo === "generar_preguntas"
        ? "Preparando tus preguntas…"
        : "Procesando tus apuntes…",
      () => vistaTema(id)
    );
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
    </div>`,
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
    "generar_preguntas",
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
      <div class="apilados">
        <button onclick="configurarExamen(${temaId})">Otro examen</button>
        <button class="secundario" onclick="vistaTema(${temaId})">← Volver al tema</button>
      </div>`);
    };

  pregunta();
}

window.addEventListener("DOMContentLoaded", () => {
  const m = location.hash.match(/^#tema-(\d+)$/);
  m ? vistaTema(Number(m[1])) : vistaTemas();
});
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
