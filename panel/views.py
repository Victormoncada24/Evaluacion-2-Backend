"""
Vistas HTML con templates propios.

Las pantallas de compra NO duplican reglas de negocio: llaman a los mismos
servicios que usa la API (ventas/services.py). Así el máximo de 5 tickets, la
reserva con temporizador y la validación de stock son idénticos en la web y
en la API.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Min, Q, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from rest_framework.exceptions import APIException, NotFound

from accounts.models import Usuario
from catalogo.models import Evento, Recinto, Sector
from ventas import services
from ventas.models import Carro, DetalleOrden, ItemCarro, Orden, Ticket

from .decorators import solo_admin, solo_espectador
from .forms import EventoAdminForm, RegistroForm

# Emoji por categoría (decoración de tarjetas, carro y tickets)
EMOJIS = {'CONCIERTO': '🎤', 'FESTIVAL': '🎪', 'TEATRO': '🎭', 'DEPORTE': '⚽', 'OTRO': '✨'}


def _texto_error(exc):
    """Convierte los errores de los servicios (excepciones de DRF) en un texto para mostrar."""
    detalle = exc.detail
    if isinstance(detalle, (list, tuple)):
        return ' '.join(str(d) for d in detalle)
    return str(detalle)


# =============================================================== PÁGINAS PÚBLICAS
def home(request):
    """Inicio PÚBLICO: portada, buscador, categorías y próximos eventos."""
    q = request.GET.get('q', '').strip()
    categoria = request.GET.get('categoria', '')

    base = (Evento.objects.filter(activo=True, fecha_inicio__gte=timezone.now())
            .select_related('recinto')
            .annotate(precio_desde=Min('sectores__precio'))
            .order_by('fecha_inicio'))
    todos = list(base)   # sin filtros: sirve para el evento destacado y las cifras de la portada

    eventos = base
    if q:
        eventos = eventos.filter(Q(titulo__icontains=q) | Q(artista__icontains=q))
    if categoria:
        eventos = eventos.filter(categoria=categoria)
    eventos = list(eventos)
    for e in eventos + todos[:1]:
        e.emoji = EMOJIS.get(e.categoria, '🎟️')

    return render(request, 'home.html', {
        'eventos': eventos, 'q': q, 'categoria': categoria,
        'categorias': [(v, l, EMOJIS.get(v, '🎟️')) for v, l in Evento.Categoria.choices],
        'proximo': todos[0] if todos else None,
        'cifras': {'eventos': len(todos),
                   'artistas': len({e.artista for e in todos}),
                   'ciudades': len({e.recinto.ciudad for e in todos})},
        'minutos_reserva': settings.MINUTOS_RESERVA, 'max_tickets': settings.MAX_TICKETS_POR_COMPRA,
    })


def evento_detalle(request, pk):
    """Detalle del evento con el mapa visual de sectores para elegir entradas."""
    evento = get_object_or_404(Evento.objects.select_related('recinto'), pk=pk, activo=True)
    evento.emoji = EMOJIS.get(evento.categoria, '🎟️')

    # Del más caro (cerca del escenario) al más barato (más lejos)
    sectores = list(Sector.objects.filter(evento=evento).con_disponibilidad().order_by('-precio'))
    n = len(sectores)
    for i, s in enumerate(sectores):
        s.tono = i % 6                                        # color del sector
        s.ancho = 55 + round(40 * i / (n - 1)) if n > 1 else 100   # más lejos = más ancho (efecto "grada")
        s.pocas = 0 < s.disponibles <= 10                     # etiqueta "últimas entradas"

    # Cuántos tickets más puede sumar a SU compra (el límite cuenta todo el carro)
    ya_en_carro, carro_usuario = 0, None
    if (request.user.is_authenticated and request.user.rol == Usuario.Rol.ESPECTADOR
            and not request.user.is_staff):
        carro_usuario = Carro.objects.filter(usuario=request.user).first()
        ya_en_carro = (ItemCarro.objects.filter(carro__usuario=request.user)
                       .aggregate(t=Sum('cantidad'))['t'] or 0)

    # Sectores numerados: asientos agrupados por fila, cada uno con su estado
    for s in sectores:
        if s.con_asientos:
            por_fila = {}
            for a in services.mapa_asientos(s, carro_usuario):
                por_fila.setdefault(a['fila'], []).append(a)
            s.mapa_filas = [{'letra': letra, 'asientos': asientos} for letra, asientos in por_fila.items()]

    return render(request, 'evento_detalle.html', {
        'evento': evento, 'sectores': sectores,
        'restantes': max(settings.MAX_TICKETS_POR_COMPRA - ya_en_carro, 0),
        'ya_en_carro': ya_en_carro, 'max_tickets': settings.MAX_TICKETS_POR_COMPRA,
        'minutos_reserva': settings.MINUTOS_RESERVA,
    })


def registro(request):
    """Crea una cuenta (Espectador u Organizador) y deja la sesión iniciada."""
    if request.user.is_authenticated:
        return redirect('home')
    form = RegistroForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        usuario = form.save()
        login(request, usuario)
        messages.success(request, f'¡Bienvenido/a a Boletaje, {usuario.username}!')
        return redirect('home')
    return render(request, 'registro.html', {'form': form})


# ============================================================ COMPRA (ESPECTADOR)
@require_POST
@solo_espectador
def agregar_al_carro(request, pk):
    """
    Recibe del mapa de sectores:
      cantidad_<id_sector> = n            (sector general)
      asiento_<id_sector>  = id (repetido, uno por asiento elegido)   (sector numerado)
    y reserva las entradas. Va dentro de UNA transacción: si un sector falla (stock,
    asiento ocupado, máximo de 5, etc.) no se agrega ninguno.
    """
    evento = get_object_or_404(Evento, pk=pk, activo=True)
    por_cantidad, por_asientos = [], []
    for clave in request.POST.keys():
        try:
            if clave.startswith('cantidad_'):
                cantidad = int(request.POST.get(clave))
                if cantidad > 0:
                    por_cantidad.append((int(clave.split('_', 1)[1]), cantidad))
            elif clave.startswith('asiento_'):
                ids = [int(v) for v in request.POST.getlist(clave)]
                if ids:
                    por_asientos.append((int(clave.split('_', 1)[1]), ids))
        except ValueError:
            continue

    if not por_cantidad and not por_asientos:
        messages.warning(request, 'Elige al menos una entrada para continuar.')
        return redirect('evento_detalle', pk=pk)

    validos = set(Sector.objects.filter(evento=evento).values_list('id', flat=True))
    try:
        with transaction.atomic():
            for sector_id, cantidad in por_cantidad:
                if sector_id not in validos:
                    raise NotFound('Uno de los sectores no pertenece a este evento.')
                services.fijar_cantidad(request.user, sector_id, cantidad, sumar=True)
            for sector_id, ids in por_asientos:
                if sector_id not in validos:
                    raise NotFound('Uno de los sectores no pertenece a este evento.')
                services.fijar_asientos(request.user, sector_id, ids, sumar=True)
    except APIException as exc:
        messages.error(request, _texto_error(exc))
        return redirect('evento_detalle', pk=pk)

    messages.success(request, f'¡Listo! Reservamos tus entradas por {settings.MINUTOS_RESERVA} minutos.')
    return redirect('carro')


@solo_espectador
def carro(request):
    """Mi carro persistente (vive en PostgreSQL) con el tiempo restante de cada reserva."""
    c = services.obtener_carro(request.user)
    ahora = timezone.now()
    items = list(c.items.select_related('sector__evento__recinto').prefetch_related('asientos')
                 .order_by('sector__evento__fecha_inicio', '-sector__precio'))
    for i in items:
        i.subtotal = i.sector.precio * i.cantidad
        i.segundos = max(int((i.expira_en - ahora).total_seconds()), 0)
        i.emoji = EMOJIS.get(i.sector.evento.categoria, '🎟️')
    return render(request, 'carro.html', {
        'items': items,
        'total': sum((i.subtotal for i in items), 0),
        'total_tickets': sum(i.cantidad for i in items),
        'max_tickets': settings.MAX_TICKETS_POR_COMPRA,
    })


@require_POST
@solo_espectador
def quitar_del_carro(request, item_id):
    try:
        services.quitar_item(request.user, item_id)
        messages.info(request, 'Quitamos la entrada de tu carro y liberamos su reserva.')
    except APIException as exc:
        messages.error(request, _texto_error(exc))
    return redirect('carro')


@require_POST
@solo_espectador
def vaciar_el_carro(request):
    services.vaciar_carro(request.user)
    messages.info(request, 'Tu carro quedó vacío.')
    return redirect('carro')


@require_POST
@solo_espectador
def pagar_carro(request):
    """Checkout: valida stock, descuenta, crea las órdenes y emite los tickets UUID."""
    try:
        services.hacer_checkout(request.user)
    except APIException as exc:
        messages.error(request, _texto_error(exc))
        return redirect('carro')
    messages.success(request, '¡Pago exitoso! Tus entradas ya están listas.')
    return redirect('mis_entradas')


@solo_espectador
def mis_entradas(request):
    """Tickets válidos del espectador (órdenes PAGADO o ENTREGADO), cada uno con su UUID."""
    tickets = list(Ticket.objects
                   .filter(orden__usuario=request.user, orden__estado__in=Orden.ESTADOS_CON_VENTA)
                   .select_related('orden__evento__recinto', 'detalle__sector', 'asiento')
                   .order_by('-creado'))
    for t in tickets:
        t.emoji = EMOJIS.get(t.orden.evento.categoria, '🎟️')
    return render(request, 'mis_entradas.html', {'tickets': tickets})


# ================================================================ ADMINISTRADOR
@solo_admin
def dashboard(request):
    """
    Dashboard del administrador. Solo cuentan órdenes PAGADO o ENTREGADO
    (las PENDIENTE y CANCELADO no son ventas reales).
    """
    validas = Orden.objects.filter(estado__in=Orden.ESTADOS_CON_VENTA)
    resumen = validas.aggregate(ingresos=Sum('total'), ordenes=Count('id'))
    ingresos = resumen['ingresos'] or 0
    n_ordenes = resumen['ordenes'] or 0
    tickets_vendidos = Ticket.objects.filter(orden__estado__in=Orden.ESTADOS_CON_VENTA).count()

    detalles = DetalleOrden.objects.filter(orden__estado__in=Orden.ESTADOS_CON_VENTA)
    ingreso_linea = ExpressionWrapper(F('cantidad') * F('precio_unitario'),
                                      output_field=DecimalField(max_digits=14, decimal_places=2))

    # ---- Ventas por categoría (la primera es "la que más se vende")
    etiquetas = dict(Evento.Categoria.choices)
    por_categoria = list(
        detalles.values(cat=F('orden__evento__categoria'))
        .annotate(tickets=Sum('cantidad'), ingresos=Sum(ingreso_linea))
        .order_by('-tickets'))
    maximo = max([c['tickets'] for c in por_categoria], default=1)
    for c in por_categoria:
        c['nombre'] = etiquetas.get(c['cat'], c['cat'])
        c['pct'] = round(c['tickets'] * 100 / maximo)
    categoria_top = por_categoria[0] if por_categoria else None

    # ---- Top 5 eventos por tickets vendidos
    top_eventos = list(
        detalles.values(titulo=F('orden__evento__titulo'))
        .annotate(tickets=Sum('cantidad'), ingresos=Sum(ingreso_linea))
        .order_by('-tickets')[:5])

    # ---- Órdenes por estado (incluye pendientes y canceladas)
    por_estado = list(Orden.objects.values('estado')
                      .annotate(n=Count('id'), monto=Sum('total')).order_by('estado'))

    # ---- Ventas de los últimos 7 días
    desde = timezone.now() - timedelta(days=7)
    por_dia = list(validas.filter(creada__gte=desde)
                   .annotate(dia=TruncDate('creada')).values('dia')
                   .annotate(ordenes=Count('id'), ingresos=Sum('total')).order_by('dia'))

    return render(request, 'dashboard.html', {
        'ingresos': ingresos, 'n_ordenes': n_ordenes, 'tickets_vendidos': tickets_vendidos,
        'ticket_promedio': (ingresos / n_ordenes) if n_ordenes else 0,
        'por_categoria': por_categoria, 'categoria_top': categoria_top,
        'top_eventos': top_eventos, 'por_estado': por_estado, 'por_dia': por_dia,
    })


def _leer_sectores(post):
    """
    Lee las filas de sectores del formulario (listas sector_nombre / precio / stock / filas / columnas).
    Si se indican filas Y asientos por fila el sector es NUMERADO y su stock se calcula solo.
    Devuelve (filas para volver a mostrar, lista de errores). Cada fila válida trae además
    n_precio, n_stock, n_filas y n_cols ya convertidos a número.
    """
    filas, errores, vistos = [], [], set()
    campos = zip(post.getlist('sector_nombre'), post.getlist('sector_precio'), post.getlist('sector_stock'),
                 post.getlist('sector_filas'), post.getlist('sector_columnas'))
    for nombre, precio, stock, nfilas, ncols in campos:
        nombre, precio, stock, nfilas, ncols = [v.strip() for v in (nombre, precio, stock, nfilas, ncols)]
        if not (nombre or precio or stock or nfilas or ncols):
            continue                                   # fila vacía: se ignora
        fila = {'nombre': nombre, 'precio': precio, 'stock': stock, 'filas': nfilas, 'columnas': ncols}
        filas.append(fila)

        numerado = bool(nfilas or ncols)
        invalido = not nombre or len(nombre) > 80 or not precio.isdigit()
        if numerado:   # filas 1-26 y asientos por fila 1-50
            invalido = invalido or not (nfilas.isdigit() and ncols.isdigit()
                                        and 1 <= int(nfilas) <= 26 and 1 <= int(ncols) <= 50)
        else:          # sector general: stock mínimo 1
            invalido = invalido or not stock.isdigit() or int(stock) < 1

        if invalido:
            errores.append(f'Sector "{nombre or "sin nombre"}": revisa nombre, precio (entero) y '
                           f'stock (mínimo 1) o filas (1-26) y asientos por fila (1-50).')
        elif nombre.lower() in vistos:
            errores.append(f'El sector "{nombre}" está repetido.')
        else:
            fila.update(n_precio=int(precio), n_filas=int(nfilas) if numerado else 0,
                        n_cols=int(ncols) if numerado else 0,
                        n_stock=int(nfilas) * int(ncols) if numerado else int(stock))
        vistos.add(nombre.lower())
    if not filas:
        errores.append('Agrega al menos un sector con su precio y stock.')
    return (filas or [{}]), errores


@solo_admin
def evento_nuevo(request):
    """
    El administrador crea un evento con su recinto y sectores en una sola pantalla.
    Todo va en UNA transacción: si algo falla no queda nada a medias.
    """
    form = EventoAdminForm(request.POST or None)
    sectores, errores_sectores = [{}], []

    if request.method == 'POST':
        sectores, errores_sectores = _leer_sectores(request.POST)
        if form.is_valid() and not errores_sectores:
            d = form.cleaned_data
            with transaction.atomic():
                recinto = d['recinto'] or Recinto.objects.create(
                    nombre=d['recinto_nombre'], direccion=d['recinto_direccion'],
                    ciudad=d['recinto_ciudad'], capacidad=d['recinto_capacidad'])
                evento = Evento.objects.create(
                    organizador=d['organizador'] or request.user, recinto=recinto,
                    titulo=d['titulo'], artista=d['artista'], categoria=d['categoria'],
                    descripcion=d['descripcion'], fecha_inicio=d['fecha_inicio'], activo=True)
                for f in sectores:
                    sector = Sector.objects.create(
                        evento=evento, nombre=f['nombre'], precio=f['n_precio'], stock=f['n_stock'],
                        filas=f['n_filas'], asientos_por_fila=f['n_cols'])
                    if sector.con_asientos:
                        sector.generar_asientos()          # crea los asientos A1, A2, ... del sector
            messages.success(request, f'Evento "{evento.titulo}" creado con {len(sectores)} sector(es).')
            return redirect('evento_detalle', pk=evento.pk)

    return render(request, 'evento_nuevo.html', {
        'form': form, 'sectores': sectores, 'errores_sectores': errores_sectores})


def pagina_no_encontrada(request, exception=None):
    """
    Manejo del 404. Se conecta de DOS formas (ver boletaje/urls.py):
      1) handler404                      -> cuando una vista levanta Http404
      2) re_path(r'^.*$', ...) al final  -> cualquier URL que ninguna ruta reconoce
    Para rutas /api/ responde JSON; para el resto, el template 404.html.
    """
    if request.path.startswith('/api/'):
        return JsonResponse({'detail': 'No encontrado.'}, status=404)
    return render(request, '404.html', status=404)
