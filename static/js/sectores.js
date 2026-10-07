/*
 * Selector visual de sectores y asientos (templates/evento_detalle.html).
 *
 * Qué hace:
 *  - Sector GENERAL: contador (+ / −); tocar el sector suma una entrada.
 *  - Sector NUMERADO: tocar el sector abre su mapa; cada asiento libre se marca/desmarca.
 *  - Respeta el máximo de tickets por compra (data-max) y las entradas disponibles de cada sector.
 *  - Calcula el total y genera campos ocultos que se envían al servidor:
 *        cantidad_<idSector> = n                 (sector general)
 *        asiento_<idSector>  = idAsiento (uno por asiento elegido)   (sector numerado)
 *
 * Ojo: es solo ayuda visual. El servidor vuelve a validar TODO (stock, máximo, asientos libres,
 * reserva) en ventas/services.py, así que alterar este script no permite saltarse las reglas.
 */
(function () {
  'use strict';

  var raiz = document.getElementById('selector');
  if (!raiz) { return; }

  var MAX = parseInt(raiz.dataset.max, 10) || 0;
  var sectores = Array.prototype.slice.call(raiz.querySelectorAll('.sector'));
  var cantidades = {};      // sector general:  { idSector: cantidad }
  var asientos = {};        // sector numerado: { idSector: { idAsiento: 'A3' } }

  var lineas = document.getElementById('lineas');
  var campos = document.getElementById('campos');       // no existe si el usuario no puede comprar
  var boton = document.getElementById('btn-agregar');   // idem
  var vacio = document.getElementById('vacio');
  var totalEl = document.getElementById('total');
  var cuentaEl = document.getElementById('cuenta');

  function formatear(n) { return '$ ' + new Intl.NumberFormat('es-CL').format(n); }
  function esNumerado(s) { return s.dataset.asientos === '1'; }
  function panelDe(s) { return s.parentElement.querySelector('.panel-asientos'); }
  function elegidosDe(s) { return Object.keys(asientos[s.dataset.id] || {}); }

  function totalTickets() {
    var t = 0;
    Object.keys(cantidades).forEach(function (k) { t += cantidades[k]; });
    Object.keys(asientos).forEach(function (k) { t += Object.keys(asientos[k]).length; });
    return t;
  }

  // Mensaje flotante breve
  function aviso(texto) {
    var t = document.createElement('div');
    t.className = 'toast';
    t.textContent = texto;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 2600);
  }

  function limiteAlcanzado() {
    aviso(MAX === 0 ? 'Ya tienes el máximo de tickets en tu carro' : 'Máximo ' + MAX + ' tickets por compra');
  }

  // Sector general: suma o resta entradas validando los límites
  function cambiar(sector, delta) {
    var id = sector.dataset.id;
    var disponibles = parseInt(sector.dataset.disp, 10);
    var nuevo = (cantidades[id] || 0) + delta;

    if (sector.classList.contains('agotado') || nuevo < 0) { return; }
    if (nuevo > disponibles) { aviso('Solo quedan ' + disponibles + ' entradas en ' + sector.dataset.nombre); return; }
    if (delta > 0 && totalTickets() >= MAX) { limiteAlcanzado(); return; }
    cantidades[id] = nuevo;
    dibujar();
  }

  // Sector numerado: marca o desmarca un asiento
  function alternarAsiento(sector, boton) {
    var id = sector.dataset.id;
    var elegidos = asientos[id] || (asientos[id] = {});
    var aid = boton.dataset.id;
    if (elegidos[aid]) {
      delete elegidos[aid];
    } else {
      if (totalTickets() >= MAX) { limiteAlcanzado(); return; }
      elegidos[aid] = boton.dataset.codigo;
    }
    boton.classList.toggle('elegido', !!elegidos[aid]);
    dibujar();
  }

  // Redibuja contadores, resumen, total y campos ocultos
  function dibujar() {
    var total = 0, cuenta = 0;
    lineas.innerHTML = '';
    if (campos) { campos.innerHTML = ''; }

    function agregarLinea(texto, subtotal) {
      var li = document.createElement('li');
      var izq = document.createElement('span');
      izq.textContent = texto;                                   // textContent: sin riesgo de inyectar HTML
      var der = document.createElement('strong');
      der.textContent = formatear(subtotal);
      li.appendChild(izq); li.appendChild(der);
      lineas.appendChild(li);
    }
    function campoOculto(nombre, valor) {
      if (!campos) { return; }
      var input = document.createElement('input');
      input.type = 'hidden'; input.name = nombre; input.value = valor;
      campos.appendChild(input);
    }

    sectores.forEach(function (s) {
      var id = s.dataset.id;
      var precio = parseInt(s.dataset.precio, 10);
      var q;

      if (esNumerado(s)) {
        var ids = elegidosDe(s);
        q = ids.length;
        var txt = s.querySelector('.txt-asientos');
        if (txt) { txt.textContent = q > 0 ? q + (q === 1 ? ' asiento elegido' : ' asientos elegidos') : 'Elegir asientos'; }
        if (q > 0) {
          agregarLinea(q + ' × ' + s.dataset.nombre + ' (' + ids.map(function (a) { return asientos[id][a]; }).join(', ') + ')', q * precio);
          ids.forEach(function (a) { campoOculto('asiento_' + id, a); });
        }
      } else {
        q = cantidades[id] || 0;
        var salida = s.querySelector('output');
        if (salida) { salida.textContent = q; }
        if (q > 0) {
          agregarLinea(q + ' × ' + s.dataset.nombre, q * precio);
          campoOculto('cantidad_' + id, q);
        }
      }
      s.classList.toggle('seleccionado', q > 0);
      total += q * precio;
      cuenta += q;
    });

    vacio.hidden = cuenta > 0;
    totalEl.textContent = formatear(total);
    cuentaEl.textContent = cuenta;
    if (boton) { boton.disabled = cuenta === 0; }
  }

  sectores.forEach(function (s) {
    if (s.classList.contains('agotado')) { return; }

    if (esNumerado(s)) {
      var panel = panelDe(s);
      // Clic en el sector (o en su botón) = abrir/cerrar el mapa de asientos
      s.addEventListener('click', function () { if (panel) { panel.hidden = !panel.hidden; } });
      if (panel) {
        panel.addEventListener('click', function (e) {
          var b = e.target.closest('.asiento');
          if (b && !b.disabled) { alternarAsiento(s, b); }
        });
      }
      return;
    }

    s.addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-accion]');
      if (btn) { cambiar(s, btn.dataset.accion === 'mas' ? 1 : -1); return; }
      cambiar(s, 1);                                             // clic en el sector = +1
    });
  });

  dibujar();
})();
