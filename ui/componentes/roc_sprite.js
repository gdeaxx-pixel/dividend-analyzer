/* Motor del sprite de ROC, la mascota de la app (16×16 pixeles).
   Fuente de diseño: Obsidian/APPs/Dividend-Analyzer/demos/roc-mascota.html (kit aprobado por
   Daniel, 24/25-sep-2026). Escrito A MANO; NO se genera. Lo inlinea `render_roc` en
   `ui/componentes/roc.html` ({{SPRITE_JS}}) y lo evalúa `tools/generar_favicon_roc.py` con node:
   una sola fuente para el componente y el favicon.
   Cada pixel sale como <rect class="pX">: el COLOR lo decide el CSS del componente con los
   tokens de la app, no este archivo. Ojos siempre `drip` (azul) en todos los estados. */
var ROC_G = ["................", "..T..........T..", "..TB........BT..", "..BBBBBBBBBBBB..",
  ".BBBBBBBBBBBBBB.", ".BEEEEBBBBEEEEB.", ".BEEEEBBBBEEEEB.", ".BEEEEBKKBEEEEB.",
  ".BEEEEBKKBEEEEB.", ".BBBBBBBBBBBBBB.", ".WBCCCCCCCCCCBW.", ".WBCCCCCCCCCCBW.",
  ".WBCCCCCCCCCCBW.", ".WBCCCCCCCCCCBW.", "..BBBBBBBBBBBB..", ".....FF..FF....."];
var ROC_R1 = [".BBEEEEBBBBEEEB.", ".BBEEPPBBBBEPPB.", ".BBEEPPBKKBEPPB.", ".BBEEEEBKKBEEEB."];
var ROC_R2 = [".BBBBBBBBBEEEEB.", ".BBBBBBBBBEEPPB.", ".BBBBBBBBBEEPPKK", ".BBBBBBBBBEEEEK."];
var ROC_BK = [".BBBBWBBBBWBBBB.", ".BBBBBWBBWBBBBB.", ".BBBBBBWWBBBBBB.", ".BBBBBBBBBBBBBB."];
function rocRev(a) { return a.map(function (r) { return r.split("").reverse().join(""); }); }
var ROC_FACES = { r1: ROC_R1, r2: ROC_R2, back: ROC_BK, l2: rocRev(ROC_R2), l1: rocRev(ROC_R1) };
var ROC_TURN = ["front", "r1", "r2", "back", "l2", "l1"];
var ROC_WING = { up: [[0, 7], [0, 8], [1, 8], [0, 9], [1, 9], [1, 10]],
  out: [[0, 10], [0, 11], [1, 10], [1, 11], [1, 12]] };
var ROC_ESTADOS = ["vigilante", "calculando", "tranquilo", "alerta", "confundido", "impuestos"];

function rocEye(g, ex, ey, dx, dy) {
  var x, y;
  for (y = ey; y < ey + 4; y++) for (x = ex; x < ex + 4; x++) g[y][x] = "E";
  for (y = ey + 1 + dy; y < ey + 3 + dy; y++) for (x = ex + 1 + dx; x < ex + 3 + dx; x++) g[y][x] = "P";
}

/* o = {st, look:[dx,dy] en -1..1, lid 0..4, lidL 0..4, face, wing:"up"|"out"|0} */
function rocGrid(o) {
  var st = o.st || "vigilante", look = o.look || [0, 0], lid = o.lid || 0;
  var face = o.face && o.face !== "front" ? o.face : null;
  var g = ROC_G.map(function (r) { return r.split(""); });
  var x, y, cl;
  var ojos = [2, 3, 4, 5, 10, 11, 12, 13];
  if (face) {
    ROC_FACES[face].forEach(function (row, i) { g[5 + i] = row.split(""); });
  } else if (st === "confundido") {
    for (y = 5; y < 9; y++) ojos.forEach(function (xx) { g[y][xx] = "B"; });
    rocEye(g, 2, 5, 0, -1); rocEye(g, 10, 4, 0, -1); g[1][2] = "."; g[0][13] = "T";
  } else {
    rocEye(g, 2, 5, look[0], look[1]); rocEye(g, 10, 5, look[0], look[1]);
    if (st === "alerta") {
      g[0][2] = "T"; g[0][13] = "T";
      [4, 5, 10, 11].forEach(function (xx) { g[5][xx] = "B"; });
      g[6][5] = "B"; g[6][10] = "B";
    }
    cl = st === "tranquilo" ? Math.max(lid, 2) : lid;
    for (y = 5; y < 5 + cl; y++) ojos.forEach(function (xx) { g[y][xx] = "L"; });
    for (y = 5; y < 5 + (o.lidL || 0); y++) [2, 3, 4, 5].forEach(function (xx) { g[y][xx] = "L"; });
  }
  if (st === "impuestos") {
    for (y = 10; y <= 14; y++) for (x = 4; x <= 11; x++) g[y][x] = "Q";
    for (x = 5; x <= 10; x++) g[11][x] = "H";
    for (x = 5; x <= 8; x++) g[13][x] = "H";
    [12, 13].forEach(function (yy) { g[yy][3] = "W"; g[yy][12] = "W"; });
  }
  if (o.wing) {
    for (y = 11; y <= 13; y++) { g[y][1] = "."; g[y][14] = "."; }
    ROC_WING[o.wing].forEach(function (p) { g[p[1]][p[0]] = "W"; g[p[1]][15 - p[0]] = "W"; });
  }
  return g;
}

/* SVG del cuadro. `hop` sube todo 1px (aleteo); `nod` baja solo la cabeza (asentir). */
function rocSvg(o, px, etiqueta) {
  var hop = o.hop || 0, nod = o.nod || 0, r = "";
  rocGrid(o).forEach(function (row, y) {
    row.forEach(function (ch, x) {
      if (ch === ".") return;
      r += '<rect class="p' + ch + '" x="' + x + '" y="' + (y - hop + (y < 10 ? nod : 0)) +
        '" width="1" height="1"/>';
    });
  });
  return '<svg viewBox="0 -1 16 17" width="' + px + '" height="' + Math.round(px * 17 / 16) +
    '" shape-rendering="crispEdges" role="img" aria-label="' + (etiqueta || "ROC") + '">' + r + "</svg>";
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { rocGrid: rocGrid, rocSvg: rocSvg, ROC_TURN: ROC_TURN, ROC_ESTADOS: ROC_ESTADOS };
}
