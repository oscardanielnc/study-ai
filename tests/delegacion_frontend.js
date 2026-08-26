// Regresion de los botones muertos. Se ejecuta con:
//     node tests/delegacion_frontend.js
//
// La CSP es `script-src 'self'` sin 'unsafe-inline', asi que el navegador
// ignora cualquier atributo onclick=. Cuando la auditoria puso la CSP, todos
// los botones pintados con innerHTML ("+ Nuevo tema", "Salir", las tarjetas,
// "Tomar examen"...) dejaron de hacer nada. Ahora declaran su accion con
// data-accion y un solo listener la despacha; esto comprueba que llega.

const fs = require("fs");
const vm = require("vm");
const RAIZ = require("path").join(__dirname, "..", "static");

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

// El listener que registra app.js: es lo que se va a disparar a mano.
let alHacerClic = null;

global.document = {
  querySelector: (sel) => nodo(sel),
  querySelectorAll: () => [],
  documentElement: { setAttribute() {}, getAttribute: () => "papel" },
  addEventListener(tipo, fn) {
    if (tipo === "click") alHacerClic = fn;
  },
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

const cajaMarked = { console };
cajaMarked.globalThis = cajaMarked;
cajaMarked.self = cajaMarked;
cajaMarked.window = cajaMarked;
vm.createContext(cajaMarked);
vm.runInContext(fs.readFileSync(`${RAIZ}/vendor/marked.min.js`, "utf8"), cajaMarked);
global.marked = cajaMarked.marked;

(0, eval)(fs.readFileSync(`${RAIZ}/app.js`, "utf8"));

let fallos = 0;
const mal = (m) => (console.error(`  ${m}`), fallos++);

// 1. El listener existe: sin el, ningun boton pintado responde.
if (typeof alHacerClic !== "function") mal("app.js no registro el listener de click");

// 2. accion() produce los atributos que el listener sabe leer.
if (accion("tema", 7) !== 'data-accion="tema" data-arg="7"')
  mal(`accion("tema", 7) devolvio: ${accion("tema", 7)}`);
if (accion("nuevo") !== 'data-accion="nuevo"')
  mal(`accion("nuevo") devolvio: ${accion("nuevo")}`);

// La tabla es `const` dentro del script, no una global: se lee de la fuente.
// De paso, eso mismo comprueba que cada accion apunta a una funcion real.
const fuente = fs.readFileSync(`${RAIZ}/app.js`, "utf8");
const tabla = fuente.slice(fuente.indexOf("const ACCIONES = {"));
const MAPA = {};
for (const m of tabla.slice(0, tabla.indexOf("};")).matchAll(
  /^\s*([a-z]+):\s*\(([a-z]*)\)\s*=>\s*([A-Za-z]+)\(/gm
)) MAPA[m[1]] = m[3];

// 3. Cada accion de la tabla llega a su funcion, con el id convertido a numero.
const llamadas = [];
for (const [nombre, fn] of Object.entries(MAPA)) {
  if (typeof global[fn] !== "function") mal(`ACCIONES.${nombre} apunta a ${fn}, que no existe`);
  global[fn] = (a) => llamadas.push([nombre, a]);
}

const clic = (accionNombre, arg) => {
  const boton = { dataset: { accion: accionNombre } };
  if (arg !== undefined) boton.dataset.arg = String(arg);
  alHacerClic({ target: { closest: () => boton }, preventDefault() {} });
};

clic("nuevo");
clic("tema", 7);
clic("borrar", 12);
if (JSON.stringify(llamadas) !== JSON.stringify([["nuevo", null], ["tema", 7], ["borrar", 12]]))
  mal(`el despacho no llego bien: ${JSON.stringify(llamadas)}`);

// 4. Un data-accion que no este en la tabla no ejecuta nada (ni revienta).
try {
  clic("noExiste");
} catch (e) {
  mal(`una accion desconocida revento: ${e.message}`);
}

// 5. Toda accion que se pinta en el HTML tiene entrada en la tabla: una
//    falta y ese boton vuelve a estar muerto, esta vez en silencio.
const usadas = new Set();
for (const m of fuente.matchAll(/data-accion="([a-z]+)"/g)) usadas.add(m[1]);
for (const m of fuente.matchAll(/accion\("([a-z]+)"/g)) usadas.add(m[1]);
for (const nombre of usadas) {
  if (!(nombre in MAPA)) mal(`el HTML usa data-accion="${nombre}" y no esta en ACCIONES`);
}

if (fallos) {
  console.error(`\nFALLO: ${fallos} problema(s) en la delegacion de clics.`);
  process.exit(1);
}
console.log(`OK: ${Object.keys(MAPA).length} acciones registradas y despachadas sin onclick=.`);
