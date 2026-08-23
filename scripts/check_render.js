/**
 * Comprueba el render del resumen: formulas y bloques [DIAGRAMA: ...].
 *
 *   node scripts/check_render.js
 *
 * Existe porque el proyecto no tiene banco de pruebas de JS y aqui se han
 * colado ya dos fallos mudos: los delimitadores \( \) no estaban declarados,
 * y marked se comia sus barras antes de que KaTeX llegara a verlas.
 */
const fs = require("fs");
global.window = {};
global.self = {};
eval(fs.readFileSync("static/vendor/marked.min.js", "utf8"));
const marked = global.marked || window.marked || module.exports.marked;

const app = fs.readFileSync("static/app.js", "utf8");
const trozo = (desde, hasta) => app.slice(app.indexOf(desde), app.indexOf(hasta));
const evalGlobal = (0, eval);
evalGlobal(trozo("function normalizarFormulas", "function renderizar"));
evalGlobal(trozo("function marcarDiagramas", "async function vistaTema(id)"));

const B = String.fromCharCode(92); // barra invertida, sin escapes que colapsen
const MD = [
  "# Ley de Ohm",
  "",
  "La corriente " + B + "(I" + B + ") es proporcional a " + B + "(V" + B + ").",
  "",
  "$$",
  "I = " + B + "frac{V}{R}",
  "$$",
  "",
  "Tambien vale $P = I^2 R$ y " + B + "[R_t = R_1 + R_2" + B + "].",
  "",
  "[DIAGRAMA: Pared del tubo digestivo con sus cuatro capas.]",
].join("\n");

const html = globalThis.marcarDiagramas(
  marked.parse(globalThis.normalizarFormulas(MD))
);

const casos = [
  ["formula inline convertida a $", html.includes("$I$") && html.includes("$V$")],
  ["la formula en bloque conserva la barra", html.includes("I = " + B + "frac{V}{R}")],
  ["\[...\] convertido a $$", html.includes("$$R_t = R_1 + R_2$$")],
  ["$...$ preservado", html.includes("$P = I^2 R$")],
  ["diagrama marcado aparte", html.includes('class="diagrama"')],
  ["sin parentesis pelados", !html.includes("corriente (I)")],
];

let fallos = 0;
for (const [nombre, ok] of casos) {
  console.log((ok ? "ok    " : "FALLA ") + nombre);
  if (!ok) fallos++;
}
if (fallos) {
  console.log("\n--- html generado ---\n" + html);
  process.exit(1);
}
console.log("\n" + casos.length + " comprobaciones pasan.");
