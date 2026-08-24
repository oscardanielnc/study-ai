const $ = (sel) => document.querySelector(sel);

/** Nada que venga del modelo, del servidor o del nombre de un archivo entra
 *  crudo en el HTML.
 *
 *  El modelo transcribe FIELMENTE lo que ve en la foto: basta con fotografiar
 *  una hoja donde ponga `<img src=x onerror=...>` para que ese texto llegue al
 *  resumen, al titulo del tema y a los enunciados. Antes se ejecutaba, y con
 *  el token de sesion en localStorage eso es robar la cuenta. */
function esc(valor) {
  return String(valor ?? "")
    .split("&").join("&amp;")
    .split("<").join("&lt;")
    .split(">").join("&gt;")
    .split('"').join("&quot;")
    .split("'").join("&#39;");
}
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

// La sesion vive en el movil y no caduca: volver a pedir la contrasena cada
// vez es justo lo que hace que la gente deje de abrir la app.
const LLAVE = "estudia.token";
const LLAVE_TEMA = "estudia.tema";

// Las mismas cuatro que acepta el servidor. El color es el del papel y el de
// la tinta, para que el boton se parezca a lo que va a pasar.
const TEMAS = [
  ["papel", "Papel", "#fbf9f4", "#1a2e44"],
  ["noche", "Noche", "#12171f", "#cfe0f5"],
  ["bosque", "Bosque", "#f4f7f1", "#1f4030"],
  ["atardecer", "Atardecer", "#fdf6f0", "#6d2f2a"],
];

/** Se aplica antes de pedir nada al servidor: si esperaramos a /yo, al abrir
 *  la app se veria un parpadeo del tema por defecto. */
function aplicarTema(nombre) {
  const tema = TEMAS.find(([id]) => id === nombre) ? nombre : "papel";
  document.documentElement.setAttribute("data-tema", tema);
  const color = TEMAS.find(([id]) => id === tema)[2];
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", color); // barra del sistema en Android
  try {
    localStorage.setItem(LLAVE_TEMA, tema);
  } catch {}
  return tema;
}

try {
  aplicarTema(localStorage.getItem(LLAVE_TEMA) || "papel");
} catch {}

function leerToken() {
  try {
    return localStorage.getItem(LLAVE) || "";
  } catch {
    return ""; // navegacion privada o almacenamiento bloqueado
  }
}

function guardarToken(valor) {
  token = valor;
  try {
    valor ? localStorage.setItem(LLAVE, valor) : localStorage.removeItem(LLAVE);
  } catch {}
}

let token = leerToken();

const SIN_SESION = ["/login", "/registro", "/yo"];

async function api(ruta, opciones = {}) {
  const cabeceras = { ...(opciones.headers || {}) };
  if (token) cabeceras.Authorization = `Bearer ${token}`;
  const r = await fetch(`/api${ruta}`, { ...opciones, headers: cabeceras });

  // Sesion revocada o borrada en el servidor: se pide entrar en vez de dejar
  // la app rota. Login y registro contestan 401 por su cuenta y no cuentan.
  if (r.status === 401 && !SIN_SESION.some((x) => ruta.startsWith(x))) {
    guardarToken("");
    vistaEntrar("Tu sesión caducó. Vuelve a entrar.");
    throw new Error("Sesión caducada");
  }
  if (!r.ok) {
    const cuerpo = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(cuerpo.detail || `Error ${r.status}`);
  }
  return r.status === 204 ? null : r.json();
}

// ---------- Entrar y registrarse ----------

// Iconos en linea: una peticion menos y heredan el color del tema.
const ICONO_PERSONA = `<svg viewBox="0 0 24 24" aria-hidden="true">
  <circle cx="12" cy="8" r="3.6"/>
  <path d="M4.8 20c0-3.6 3.2-5.8 7.2-5.8s7.2 2.2 7.2 5.8"/></svg>`;
const ICONO_SALIDA = `<svg viewBox="0 0 24 24" aria-hidden="true">
  <path d="M14.5 4.5H6.5a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h8"/>
  <path d="M17 8.5 20.5 12 17 15.5"/><path d="M20 12h-9"/></svg>`;

function pintarSesion(usuario) {
  $("#sesion").innerHTML = usuario
    ? `<button class="quien" onclick="vistaPerfil()" aria-label="Ajustes de perfil">
         ${ICONO_PERSONA}<span>${esc(usuario)}</span>
       </button>
       <button class="salir" onclick="pedirSalir()">
         ${ICONO_SALIDA}<span>Salir</span>
       </button>`
    : "";
}

function pedirSalir() {
  confirmar(
    `\u00bfCerrar sesi\u00f3n?<br>
     <small>Tendr\u00e1s que volver a escribir tu usuario y tu contrase\u00f1a.</small>`,
    salir,
    "Salir"
  );
}

async function salir() {
  try {
    await api("/salir", { method: "POST" });
  } catch {}
  guardarToken("");
  vistaEntrar();
}

let registrando = false;

function vistaEntrar(aviso = "") {
  location.hash = "";
  pintarSesion("");
  const verbo = registrando ? "Crear cuenta" : "Entrar";
  pintar(`
    <div class="entrar">
      <h1>Estudia</h1>
      <p class="lema">Tus apuntes, resumidos y convertidos en examen.</p>
      <form id="acceso" autocomplete="on">
        <label for="usuario">Usuario</label>
        <input id="usuario" name="username" autocomplete="username"
          autocapitalize="none" autocorrect="off" spellcheck="false" required>
        <label for="clave">Contraseña</label>
        <input id="clave" name="password" type="password" required
          autocomplete="${registrando ? "new-password" : "current-password"}">
        <p class="error ${aviso ? "" : "oculto"}" id="aviso">${aviso}</p>
        <button type="submit" id="enviar">${verbo}</button>
      </form>
      <button class="fantasma" onclick="alternarAcceso()">${
        registrando
          ? "Ya tengo cuenta"
          : "No tengo cuenta, quiero registrarme"
      }</button>
    </div>`);
  $("#acceso").onsubmit = acceder;
}

function alternarAcceso() {
  registrando = !registrando;
  vistaEntrar();
}

async function acceder(evento) {
  evento.preventDefault();
  const usuario = $("#usuario").value.trim();
  const clave = $("#clave").value;
  const boton = $("#enviar");
  boton.disabled = true;
  boton.textContent = "Un momento…";
  try {
    const r = await api(registrando ? "/registro" : "/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ usuario, clave }),
    });
    guardarToken(r.token);
    if (r.tema_visual) aplicarTema(r.tema_visual);
    pintarSesion(r.usuario);
    vistaTemas();
  } catch (e) {
    // Se repinta el aviso sin perder lo escrito: reescribir la contrasena en
    // el movil por un error de dedo es de las cosas mas molestas que hay.
    boton.disabled = false;
    boton.textContent = registrando ? "Crear cuenta" : "Entrar";
    const aviso = $("#aviso");
    if (aviso) {
      aviso.textContent = e.message;
      aviso.classList.remove("oculto");
    }
  }
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
    $("#frase").innerHTML = `${esc(frase)} <span class="reloj">${reloj}</span>`;
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
function confirmar(html, alSi, verbo = "Eliminar") {
  const fondo = document.createElement("div");
  fondo.className = "modal";
  fondo.innerHTML = `<div class="hoja">
      <div class="dice">${html}</div>
      <button class="peligro" id="si">${verbo}</button>
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
  // `mensaje` ya viene escapado por quien lo compone, porque a veces
  // lleva <br> y <small> a proposito.
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

// ---------- Perfil ----------

/** Un solo sitio para el nombre, la contrasena y el aspecto. Se llega desde el
 *  icono de la cabecera. */
function vistaPerfil() {
  const actual = document.documentElement.getAttribute("data-tema") || "papel";
  const quien = $("#sesion .quien span");
  pintar(`
    <button class="volver" onclick="vistaTemas()">\u2190 Temas</button>
    <h1 class="titulo-pantalla">Tu perfil</h1>

    <form class="grupo" id="f-nombre">
      <h2>Nombre de usuario</h2>
      <input id="p-usuario" name="username" autocomplete="username"
        autocapitalize="none" autocorrect="off" spellcheck="false"
        value="${esc(quien ? quien.textContent : "")}" required>
      <p class="dicho" id="d-nombre"></p>
      <button type="submit">Guardar nombre</button>
    </form>

    <form class="grupo" id="f-clave">
      <h2>Contrase\u00f1a</h2>
      <label for="p-actual">Contrase\u00f1a actual</label>
      <input id="p-actual" type="password" autocomplete="current-password" required>
      <label for="p-nueva">Contrase\u00f1a nueva</label>
      <input id="p-nueva" type="password" autocomplete="new-password" required>
      <p class="dicho" id="d-clave"></p>
      <button type="submit">Cambiar contrase\u00f1a</button>
    </form>

    <div class="grupo">
      <h2>Aspecto</h2>
      <div class="paletas">
        ${TEMAS.map(
          ([id, nombre, papel, tinta]) => `
          <button class="paleta" data-tema-id="${id}"
            aria-pressed="${id === actual}"
            style="background:${papel};color:${tinta};border-color:${tinta}33">
            <span class="muestra" style="background:${tinta}"></span>
            <span>${nombre}</span>
          </button>`
        ).join("")}
      </div>
      <p class="dicho" id="d-tema"></p>
    </div>`);

  $("#f-nombre").onsubmit = guardarNombre;
  $("#f-clave").onsubmit = guardarClave;
  document.querySelectorAll(".paleta").forEach((b) => {
    b.onclick = () => elegirTema(b.dataset.temaId);
  });
}

/** Un aviso junto al campo que lo provoca, no una pantalla de error: en
 *  ajustes se cambian varias cosas seguidas y no hay que perder el sitio. */
function decir(id, mensaje, mal = false) {
  const p = $(id);
  if (!p) return;
  p.textContent = mensaje;
  p.className = `dicho ${mal ? "mal" : "bien"}`;
}

async function guardarNombre(evento) {
  evento.preventDefault();
  const usuario = $("#p-usuario").value.trim();
  try {
    const r = await api("/perfil", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ usuario }),
    });
    pintarSesion(r.usuario);
    decir("#d-nombre", "Guardado.");
  } catch (e) {
    decir("#d-nombre", e.message, true);
  }
}

async function guardarClave(evento) {
  evento.preventDefault();
  try {
    await api("/perfil/clave", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        actual: $("#p-actual").value,
        nueva: $("#p-nueva").value,
      }),
    });
    $("#f-clave").reset();
    decir("#d-clave", "Contrase\u00f1a cambiada. Las sesiones de otros"
      + " dispositivos se han cerrado.");
  } catch (e) {
    decir("#d-clave", e.message, true);
  }
}

async function elegirTema(id) {
  // Se aplica ya y se guarda despues: el color tiene que cambiar al tocarlo,
  // no cuando conteste el servidor.
  aplicarTema(id);
  document
    .querySelectorAll(".paleta")
    .forEach((b) => b.setAttribute("aria-pressed", b.dataset.temaId === id));
  try {
    await api("/perfil", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tema_visual: id }),
    });
    decir("#d-tema", "Te acompa\u00f1ar\u00e1 en cualquier dispositivo.");
  } catch (e) {
    decir("#d-tema", `Se ve as\u00ed en este m\u00f3vil, pero no se pudo guardar: ${e.message}`, true);
  }
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
          <h3>${esc(t.titulo)}</h3>
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

/** Un tema que no llego a tener resumen no se guarda: una tarjeta
 *  "Procesando..." cuyo unico contenido es "Sin resumen" no le sirve a nadie.
 *  Se cuenta el error y se tira. */
async function descartarTema(id, error) {
  location.hash = "";
  try {
    await api(`/temas/${id}`, { method: "DELETE" });
  } catch {}
  fallo(
    `No se pudieron procesar tus apuntes, así que no se guardó el tema.
     Vuelve a intentarlo.<br><small>${esc(error)}</small>`,
    "vistaTemas()"
  );
}

/** Borrar es irreversible y la papelera esta pegada a la tarjeta: siempre
 *  se pregunta, y se dice exactamente que se lleva por delante. */
function pedirBorrar(id) {
  const titulo = $(`.tarjeta[data-id="${id}"] h3`).textContent;
  confirmar(
    `¿Eliminar <b>${esc(titulo)}</b>?<br>
     <small>Se borran su resumen, sus preguntas y su historial de exámenes.
     No se puede deshacer.</small>`,
    async () => {
      try {
        await api(`/temas/${id}`, { method: "DELETE" });
      } catch (e) {
        return fallo(esc(e.message), "vistaTemas()");
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
    if (token) x.setRequestHeader("Authorization", `Bearer ${token}`);
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
      seguirJob(
        job_id,
        "transcribir",
        "Procesando tus apuntes…",
        () => vistaTema(tema_id),
        (error) => descartarTema(tema_id, error)
      );
    } catch (e) {
      fallo(esc(e.message), "vistaTemas()");
    }
  };
  input.click();
}

/** El trabajo ocurre entero en el servidor; esto solo mira. Por eso apagar la
 *  pantalla, cambiar de pestana o recargar ya no lo interrumpe: como mucho se
 *  deja de mirar un rato. Un fallo de red suelto tampoco lo mata: se insiste. */
const REINTENTOS = 60; // ~5 min de red caida antes de rendirse

function seguirJob(jobId, tipo, titulo, alTerminar, alFallar) {
  // Las preguntas no se generan de una en una: el modelo devuelve el lote
  // entero de golpe. Un "0 / 10" clavado tres minutos solo confunde, asi que
  // ahi no hay contador: el titulo ya dice cuantas y de que nivel.
  const conContador = tipo !== "generar_preguntas";
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
      conContador ? `${j.progreso_actual} / ${j.progreso_total}` : ""
    );
    if (j.estado === "completado") return alTerminar();
    if (j.estado === "fallido") {
      return alFallar
        ? alFallar(j.error)
        : fallo(
            `No se pudo terminar.<br><small>${esc(j.error)}</small>`,
            "vistaTemas()"
          );
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
    return fallo(esc(e.message), "vistaTemas()");
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
      () => vistaTema(id),
      job.tipo === "transcribir" ? (error) => descartarTema(id, error) : undefined
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
  // Se escapa ANTES de marked: marked v15 deja pasar el HTML crudo tal cual
  // (quito `sanitize` en la v8) y aqui no queremos HTML del modelo, solo
  // Markdown. Escapado, `<img onerror>` se lee como texto y el Markdown y el
  // LaTeX siguen funcionando igual.
  destino.innerHTML = marcarDiagramas(
    marked.parse(esc(normalizarFormulas(t.resumen_md || "_Sin resumen._")))
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
    return fallo(esc(e.message), `vistaTema(${temaId})`);
  }

  if (r.examen_id) return vistaExamen(temaId, r);

  const plural = r.faltan === 1 ? "" : "s";
  const nivel = (NIVELES.find(([v]) => v === elegido.nivel) || [, ""])[1];
  seguirJob(
    r.job_id,
    "generar_preguntas",
    `Formulando ${r.faltan} pregunta${plural} de nivel ${nivel.toLowerCase()}…`,
    async () => {
      try {
        vistaExamen(temaId, await api(`/temas/${temaId}/examenes`, peticion));
      } catch (e) {
        fallo(esc(e.message), `vistaTema(${temaId})`);
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
      <div class="enunciado">${esc(p.enunciado)}</div>
      <div id="opciones">${p.opciones
        .map(
          (o, k) =>
            `<button class="opcion" data-k="${k}"><span>${esc(o)}</span>
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
      return fallo(esc(e.message), `vistaTema(${temaId})`);
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
    fb.innerHTML = `<div class="porque"><h4>Por qué</h4>${esc(r.justificacion)}</div>
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

window.addEventListener("DOMContentLoaded", async () => {
  // /yo devuelve null en vez de 401: al abrir la app no hay ningun error que
  // ensenar, simplemente aun no se ha entrado.
  let quien = null;
  try {
    quien = await api("/yo");
  } catch {}
  if (!quien) return vistaEntrar();
  aplicarTema(quien.tema_visual);
  pintarSesion(quien.usuario);
  const m = location.hash.match(/^#tema-(\d+)$/);
  m ? vistaTema(Number(m[1])) : vistaTemas();
});
// `updateViaCache: "none"` obliga a pedir sw.js a la red. Cloudflare le pone
// un max-age de 4 h que el navegador respetaria, y hasta ahora un despliegue
// tardaba esas 4 h en llegar al movil. Ademas se revisa al volver a la app.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker
    .register("/sw.js", { updateViaCache: "none" })
    .then((reg) => {
      document.addEventListener("visibilitychange", () => {
        if (!document.hidden) reg.update();
      });
    })
    .catch(() => {});
}
