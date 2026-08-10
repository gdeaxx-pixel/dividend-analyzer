"""Script de auto-alto compartido por los 5 extractores de componentes.

`components.html()` fija el alto del iframe desde Python y no se adapta al contenido, así
que cada componente reservaba cientos de píxeles de vacío. Este bloque va al final de cada
plantilla y hace que el componente corrija su propio alto desde dentro.

Es un string PLANO a propósito, no parte de una f-string: así las llaves del JS van simples
y no hay que doblarlas. Los extractores lo interpolan con `{AUTO_ALTO_JS}`.
"""

AUTO_ALTO_JS = """<script>
/* Auto-alto del iframe. `components.html` fija el alto desde Python y no se adapta al
   contenido, así que cada componente reservaba cientos de píxeles de vacío. El iframe es
   same-origin (`srcdoc`), así que desde aquí se alcanza el propio <iframe> del documento
   padre y se le corrige el alto. NO se usa `streamlit:setFrameHeight`: ese canal es de
   componentes registrados con `declare_component`, no de `components.html`.
   Se mide `body.scrollHeight` y NO `documentElement.scrollHeight`: el segundo nunca baja
   del alto del viewport del iframe, así que nunca detectaría el vacío. */
(function () {
  "use strict";
  var fe = null;
  try { fe = window.frameElement; } catch (e) { fe = null; }
  if (!fe) return;   // cross-origin o abierto suelto: se queda el alto que fijó Python
  var aplicado = 0;
  function ajustar() {
    var h = Math.ceil(document.body.scrollHeight);
    if (!h || Math.abs(h - aplicado) <= 1) return;
    aplicado = h;
    fe.setAttribute("height", String(h));
    fe.style.height = h + "px";
  }
  window.__vdAjustarAlto = ajustar;
  ajustar();
  [60, 200, 500, 1200].forEach(function (ms) { setTimeout(ajustar, ms); });
  window.addEventListener("resize", ajustar);
  if (window.ResizeObserver) {
    /* Referencia fuerte a propósito: un ResizeObserver sin referencia puede recolectarse
       y dejar de avisar en silencio. */
    var ro = new ResizeObserver(ajustar);
    ro.observe(document.body);
    window.__vdAltoRO = ro;
  }
  /* Red de seguridad: ni el panel de navegador embebido ni Chrome headless disparan
     ResizeObserver ni `resize`. Los temporizadores sí corren en todos esos entornos. */
  setInterval(ajustar, 1000);
})();
</script>
"""
