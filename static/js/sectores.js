/*
 * Selector visual de sectores (templates/evento_detalle.html).
 *
 * Qué hace:
 *  - Cada sector tiene un contador (+ / −); tocar el sector suma una entrada.
 *  - Respeta el máximo de tickets por compra (data-max) y las entradas disponibles de cada sector.
 *  - Calcula el total y genera campos ocultos `cantidad_<id>` que se envían al servidor.
 *
 * Ojo: es solo ayuda visual. El servidor vuelve a validar TODO (stock, máximo, reserva)
 * en ventas/services.py, así que alterar este script no permite saltarse las reglas.
 */
(function () {
  'use strict';

  var raiz = document.getElementById('selector');
  if (!raiz) { return; }

  var MAX = parseInt(raiz.dataset.max, 10) || 0;
  var sectores = Array.prototype.slice.call(raiz.querySelectorAll('.sector'));
  var cantidades = {};                       // { idSector: cantidad elegida }

  var lineas = document.getElementById('lineas');
  var campos = document.getElementById('campos');       // no existe si el usuario no puede comprar
  var boton = document.getElementById('btn-agregar');   // idem
  var vacio = document.getElementById('vacio');
  var totalEl = document.getElementById('total');
  var cuentaEl = document.getElementById('cuenta');

  function formatear(n) { return '$ ' + new Intl.NumberFormat('es-CL').format(n); }

  function totalTickets() {
    return Object.keys(cantidades).reduce(function (a, k) { return a + cantidades[k]; }, 0);
  }

  // Mensaje flotante breve
  function aviso(texto) {
    var t = document.createElement('div');
    t.className = 'toast';
    t.textContent = texto;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 2600);
  }

  // Suma o resta entradas de un sector validando los límites
  function cambiar(sector, delta) {
    var id = sector.dataset.id;
    var disponibles = parseInt(sector.dataset.disp, 10);
    var actual = cantidades[id] || 0;
    var nuevo = actual + delta;

    if (sector.classList.contains('agotado')) { return; }
    if (nuevo < 0) { return; }
    if (nuevo > disponibles) { aviso('Solo quedan ' + disponibles + ' entradas en ' + sector.dataset.nombre); return; }
    if (delta > 0 && totalTickets() >= MAX) {
      aviso(MAX === 0 ? 'Ya tienes el máximo de tickets en tu carro' : 'Máximo ' + MAX + ' tickets por compra');
      return;
    }
    cantidades[id] = nuevo;
    dibujar();
  }

  // Redibuja contadores, resumen, total y campos ocultos
  function dibujar() {
    var total = 0, cuenta = 0;
    lineas.innerHTML = '';
    if (campos) { campos.innerHTML = ''; }

    sectores.forEach(function (s) {
      var id = s.dataset.id;
      var q = cantidades[id] || 0;
      var salida = s.querySelector('output');
      if (salida) { salida.textContent = q; }
      s.classList.toggle('seleccionado', q > 0);
      if (q === 0) { return; }

      var subtotal = q * parseInt(s.dataset.precio, 10);
      total += subtotal;
      cuenta += q;

      var li = document.createElement('li');
      var izq = document.createElement('span');
      izq.textContent = q + ' × ' + s.dataset.nombre;          // textContent: sin riesgo de inyectar HTML
      var der = document.createElement('strong');
      der.textContent = formatear(subtotal);
      li.appendChild(izq); li.appendChild(der);
      lineas.appendChild(li);

      if (campos) {
        var input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'cantidad_' + id;
        input.value = q;
        campos.appendChild(input);
      }
    });

    vacio.hidden = cuenta > 0;
    totalEl.textContent = formatear(total);
    cuentaEl.textContent = cuenta;
    if (boton) { boton.disabled = cuenta === 0; }
  }

  sectores.forEach(function (s) {
    s.addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-accion]');
      if (btn) { cambiar(s, btn.dataset.accion === 'mas' ? 1 : -1); return; }
      cambiar(s, 1);                                            // clic en el sector = +1
    });
  });

  dibujar();
})();
