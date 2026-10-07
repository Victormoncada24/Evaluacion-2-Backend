"""
Lógica de negocio del carro y las órdenes (capa de servicios).

Todo lo que toca stock o asientos corre dentro de transaction.atomic() y bloquea
las filas con select_for_update(). Eso garantiza que dos compradores simultáneos no
puedan vender la misma última entrada (ni el mismo asiento): o se confirma todo,
o no se confirma nada.

Dos tipos de sector:
  * GENERAL   -> el comprador elige una CANTIDAD.
  * NUMERADO  -> el comprador elige ASIENTOS concretos (cantidad = nº de asientos).
En ambos casos el stock del sector solo baja al pasar la orden a PAGADO.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from catalogo.models import Asiento, Sector

from .models import Carro, DetalleOrden, ItemCarro, Orden, Ticket

MAX_TICKETS = settings.MAX_TICKETS_POR_COMPRA
ReservaAsiento = ItemCarro.asientos.through   # tabla intermedia ItemCarro <-> Asiento


# ------------------------------------------------------------------ utilidades
def obtener_carro(usuario):
    """Devuelve el carro del usuario; lo crea la primera vez (relación 1:1)."""
    carro, _ = Carro.objects.get_or_create(usuario=usuario)
    return carro


def _reservado_por_otros(sector_id, carro):
    """Tickets del sector retenidos por OTROS carros con reserva vigente."""
    total = (ItemCarro.objects
             .filter(sector_id=sector_id, expira_en__gt=timezone.now())
             .exclude(carro=carro)
             .aggregate(t=Sum('cantidad'))['t'])
    return total or 0


def _validar_evento_vendible(evento):
    if not evento.activo or evento.fecha_inicio <= timezone.now():
        raise ValidationError('El evento no está disponible para la venta.')


def _asientos_no_libres(sector_id, carro):
    """
    Ids de asientos del sector que ESTE carro no puede tomar:
      - vendidos (tickets de órdenes PAGADO/ENTREGADO; una orden CANCELADA libera el asiento)
      - reservados por OTROS carros con reserva vigente
    """
    vendidos = set(Ticket.objects
                   .filter(asiento__sector_id=sector_id, orden__estado__in=Orden.ESTADOS_CON_VENTA)
                   .values_list('asiento_id', flat=True))
    reservados = set(ReservaAsiento.objects
                     .filter(itemcarro__sector_id=sector_id, itemcarro__expira_en__gt=timezone.now())
                     .exclude(itemcarro__carro=carro)
                     .values_list('asiento_id', flat=True))
    return vendidos | reservados


def mapa_asientos(sector, carro=None):
    """
    Estado de cada asiento de un sector numerado (lo usan la web y la API):
      LIBRE · RESERVADO (otra persona) · VENDIDO · EN_TU_CARRO (reserva vigente tuya)
    """
    vendidos = set(Ticket.objects
                   .filter(asiento__sector=sector, orden__estado__in=Orden.ESTADOS_CON_VENTA)
                   .values_list('asiento_id', flat=True))
    reservados, mios = set(), set()
    filas = (ReservaAsiento.objects
             .filter(itemcarro__sector=sector, itemcarro__expira_en__gt=timezone.now())
             .values_list('asiento_id', 'itemcarro__carro_id'))
    for asiento_id, carro_id in filas:
        (mios if carro is not None and carro_id == carro.pk else reservados).add(asiento_id)

    mapa = []
    for a in sector.asientos.all():
        if a.pk in vendidos:
            estado = 'VENDIDO'
        elif a.pk in mios:
            estado = 'EN_TU_CARRO'
        elif a.pk in reservados:
            estado = 'RESERVADO'
        else:
            estado = 'LIBRE'
        mapa.append({'id': a.pk, 'fila': a.fila, 'numero': a.numero, 'etiqueta': a.etiqueta, 'estado': estado})
    return mapa


# ----------------------------------------------------------------------- carro
def _bloquear(usuario, sector_id):
    """
    Bloquea el carro del usuario y el sector (siempre en este orden, para evitar
    deadlocks). Nadie más reserva ni paga este sector hasta terminar la transacción.
    """
    carro = Carro.objects.select_for_update().get(pk=obtener_carro(usuario).pk)
    sector = (Sector.objects.select_for_update(of=('self',)).select_related('evento')
              .filter(pk=sector_id).first())
    if sector is None:
        raise NotFound('El sector no existe.')
    _validar_evento_vendible(sector.evento)
    return carro, sector


def _guardar_item(carro, sector, cantidad, asientos=None):
    """
    Guarda el ítem y reinicia el temporizador de reserva.
    Solo se renuevan los ítems con reserva vigente: uno ya vencido no "resucita"
    sin volver a validarse (podría haberlo reservado otra persona).
    """
    ahora = timezone.now()
    nueva_expiracion = ahora + timedelta(minutes=settings.MINUTOS_RESERVA)
    carro.items.filter(expira_en__gt=ahora).update(expira_en=nueva_expiracion)
    item, _ = ItemCarro.objects.update_or_create(
        carro=carro, sector=sector,
        defaults={'cantidad': cantidad, 'expira_en': nueva_expiracion})
    if asientos is not None:
        item.asientos.set(list(asientos))
    carro.save(update_fields=['actualizado'])


@transaction.atomic
def fijar_cantidad(usuario, sector_id, cantidad, sumar=False):
    """
    SECTOR GENERAL: agrega o modifica la cantidad de un ítem y reserva las entradas.
      sumar=True  -> `cantidad` se suma a lo que ya había (POST)
      sumar=False -> `cantidad` pasa a ser el total del sector (PATCH)
    """
    carro, sector = _bloquear(usuario, sector_id)
    if sector.con_asientos:
        raise ValidationError(f'El sector "{sector.nombre}" tiene asientos numerados: elige tus asientos.')

    existente = carro.items.filter(sector=sector).values_list('cantidad', flat=True).first() or 0
    if sumar:
        cantidad += existente

    # Regla: máximo MAX_TICKETS tickets por compra (suma de todo el carro)
    en_otros_sectores = carro.items.exclude(sector=sector).aggregate(t=Sum('cantidad'))['t'] or 0
    if en_otros_sectores + cantidad > MAX_TICKETS:
        raise ValidationError(f'Máximo {MAX_TICKETS} tickets por compra.')

    # Disponibilidad = stock real - reservas vigentes de OTROS usuarios
    disponibles = sector.stock - _reservado_por_otros(sector.id, carro)
    if cantidad > max(disponibles, 0):
        raise ValidationError(f'Solo quedan {max(disponibles, 0)} entradas disponibles en "{sector.nombre}".')

    _guardar_item(carro, sector, cantidad)
    return carro


@transaction.atomic
def fijar_asientos(usuario, sector_id, asiento_ids, sumar=False):
    """
    SECTOR NUMERADO: reserva asientos concretos.
      sumar=True  -> se agregan a los que ya tenía en ese sector (POST)
      sumar=False -> la lista pasa a ser exactamente la elegida (PATCH; vacía = quitar)
    """
    carro, sector = _bloquear(usuario, sector_id)
    if not sector.con_asientos:
        raise ValidationError(f'El sector "{sector.nombre}" no tiene asientos numerados: indica la cantidad.')

    pedidos = set(asiento_ids)
    validos = set(Asiento.objects.filter(sector=sector, pk__in=pedidos).values_list('pk', flat=True))
    if validos != pedidos:
        raise ValidationError('Alguno de los asientos no pertenece a este sector.')

    item = carro.items.filter(sector=sector).first()
    actuales = set(item.asientos.values_list('pk', flat=True)) if item else set()
    finales = (actuales | pedidos) if sumar else pedidos

    if not finales:                                   # lista vacía: se quita el sector del carro
        carro.items.filter(sector=sector).delete()
        carro.save(update_fields=['actualizado'])
        return carro

    en_otros_sectores = carro.items.exclude(sector=sector).aggregate(t=Sum('cantidad'))['t'] or 0
    if en_otros_sectores + len(finales) > MAX_TICKETS:
        raise ValidationError(f'Máximo {MAX_TICKETS} tickets por compra.')

    # Ningún asiento puede estar vendido ni reservado por otra persona
    ocupados = finales & _asientos_no_libres(sector.id, carro)
    if ocupados:
        codigos = ', '.join(sorted(a.codigo for a in Asiento.objects.filter(pk__in=ocupados)))
        raise ValidationError(f'Estos asientos ya no están disponibles: {codigos}.')

    _guardar_item(carro, sector, len(finales), asientos=finales)
    return carro


@transaction.atomic
def quitar_item(usuario, item_id):
    carro = Carro.objects.select_for_update().filter(usuario=usuario).first()
    if carro is None:
        raise NotFound('Tu carro está vacío.')
    borrados, _ = carro.items.filter(pk=item_id).delete()   # sus asientos reservados se liberan solos
    if not borrados:
        raise NotFound('Ese ítem no está en tu carro.')
    carro.save(update_fields=['actualizado'])
    return carro


@transaction.atomic
def vaciar_carro(usuario):
    """Quita todos los ítems del carro (libera todas sus reservas)."""
    carro = obtener_carro(usuario)
    carro.items.all().delete()
    carro.save(update_fields=['actualizado'])
    return carro


# -------------------------------------------------------------------- checkout
@transaction.atomic
def hacer_checkout(usuario):
    """
    Convierte el carro en Orden(es) PAGADAS y devuelve una lista.
    Como el carro puede mezclar eventos de distintos organizadores, se crea
    UNA orden por evento (así cada organizador gestiona solo las suyas).
    Todo ocurre en UNA transacción: si cualquier paso falla, no queda nada a medias.
    """
    carro = Carro.objects.select_for_update().filter(usuario=usuario).first()
    items = list(carro.items.select_related('sector__evento')) if carro else []
    if not items:
        raise ValidationError('Tu carro está vacío.')

    if sum(i.cantidad for i in items) > MAX_TICKETS:
        raise ValidationError(f'Máximo {MAX_TICKETS} tickets por compra.')
    for item in items:
        _validar_evento_vendible(item.sector.evento)

    # Bloqueo ordenado por id (evita deadlocks entre compras simultáneas)
    sectores = {s.id: s for s in Sector.objects.select_for_update()
                .filter(pk__in=[i.sector_id for i in items]).order_by('pk')}

    # Validación: stock real - reservas de otros y, en sectores numerados, que los
    # asientos sigan libres. Si falla CUALQUIER ítem se rechaza todo el pago (rollback).
    for item in items:
        sector = sectores[item.sector_id]
        disponibles = sector.stock - _reservado_por_otros(sector.id, carro)
        if item.cantidad > disponibles:
            raise ValidationError(f'Ya no hay stock suficiente en "{sector.nombre}" (quedan {max(disponibles, 0)}).')
        if sector.con_asientos:
            ids = set(item.asientos.values_list('pk', flat=True))
            if len(ids) != item.cantidad:
                raise ValidationError(f'Elige los asientos de "{sector.nombre}" antes de pagar.')
            if ids & _asientos_no_libres(sector.id, carro):
                raise ValidationError(f'Algunos asientos de "{sector.nombre}" ya no están disponibles.')

    # Agrupamos los ítems por evento y generamos una orden por cada uno
    por_evento = {}
    for item in items:
        por_evento.setdefault(item.sector.evento_id, []).append(item)

    ordenes = []
    for evento_items in por_evento.values():
        evento = evento_items[0].sector.evento
        total = sum((sectores[i.sector_id].precio * i.cantidad for i in evento_items), Decimal('0'))
        # Orden PENDIENTE + detalle con el precio congelado de este instante...
        orden = Orden.objects.create(usuario=usuario, evento=evento,
                                     estado=Orden.Estado.PENDIENTE, total=total)
        for item in evento_items:
            sector = sectores[item.sector_id]
            detalle = DetalleOrden.objects.create(orden=orden, sector=sector, cantidad=item.cantidad,
                                                  precio_unitario=sector.precio)
            if sector.con_asientos:
                detalle.asientos.set(item.asientos.all())      # los asientos viajan a la orden
        # ...y se "paga" (aquí iría la pasarela de pago real; está simulada).
        ordenes.append(pagar_orden(orden))

    # El carro queda vacío pero SIGUE existiendo (1:1 con el usuario)
    carro.items.all().delete()
    carro.save(update_fields=['actualizado'])
    return ordenes


@transaction.atomic
def pagar_orden(orden):
    """
    PENDIENTE -> PAGADO. Es el ÚNICO lugar donde se descuenta stock y se
    generan los tickets con UUID (y su asiento, en sectores numerados).
    """
    if orden.estado != Orden.Estado.PENDIENTE:
        raise ValidationError('Solo se puede pagar una orden pendiente.')

    detalles = list(orden.detalles.prefetch_related('asientos'))
    sectores = {s.id: s for s in Sector.objects.select_for_update()
                .filter(pk__in=[d.sector_id for d in detalles]).order_by('pk')}

    # Validación atómica: con las filas bloqueadas, lo leído es lo real
    for d in detalles:
        sector = sectores[d.sector_id]
        if sector.stock < d.cantidad:
            raise ValidationError(f'Sin stock en "{sector.nombre}".')
        if sector.con_asientos:
            ids = [a.pk for a in d.asientos.all()]
            if len(ids) != d.cantidad:
                raise ValidationError(f'La orden no tiene todos sus asientos asignados en "{sector.nombre}".')
            if Ticket.objects.filter(asiento_id__in=ids, orden__estado__in=Orden.ESTADOS_CON_VENTA).exists():
                raise ValidationError(f'Algunos asientos de "{sector.nombre}" ya fueron vendidos.')

    for d in detalles:
        sector = sectores[d.sector_id]
        sector.stock -= d.cantidad
        sector.save(update_fields=['stock'])

    # Un Ticket por cada entrada comprada (el UUID se genera solo)
    tickets = []
    for d in detalles:
        if sectores[d.sector_id].con_asientos:
            tickets += [Ticket(orden=orden, detalle=d, asiento=a) for a in d.asientos.all()]
        else:
            tickets += [Ticket(orden=orden, detalle=d) for _ in range(d.cantidad)]
    Ticket.objects.bulk_create(tickets)

    orden.estado = Orden.Estado.PAGADO
    orden.save(update_fields=['estado', 'actualizada'])
    return orden


# --------------------------------------------------- cambios de estado (organizador)
# Máquina de estados: desde cada estado, a cuáles se puede avanzar
TRANSICIONES = {
    Orden.Estado.PENDIENTE: {Orden.Estado.CANCELADO},
    Orden.Estado.PAGADO: {Orden.Estado.CANCELADO, Orden.Estado.ENTREGADO},
    Orden.Estado.CANCELADO: set(),   # estado final
    Orden.Estado.ENTREGADO: set(),   # estado final
}


@transaction.atomic
def cambiar_estado_orden(orden_id, nuevo_estado, organizador):
    """El organizador marca una orden de SU evento como CANCELADO o ENTREGADO."""
    orden = (Orden.objects.select_for_update(of=('self',))
             .filter(pk=orden_id, evento__organizador=organizador).first())
    if orden is None:
        raise NotFound('Orden no encontrada.')   # incluye órdenes de otros organizadores

    if nuevo_estado not in TRANSICIONES[orden.estado]:
        raise ValidationError(f'No se puede pasar de {orden.estado} a {nuevo_estado}.')

    # Cancelar una orden PAGADA repone el stock automáticamente. Los asientos quedan
    # libres solos: se consideran vendidos solo mientras la orden esté PAGADO/ENTREGADO.
    # (Una PENDIENTE nunca descontó stock, así que no hay nada que reponer.)
    if orden.estado == Orden.Estado.PAGADO and nuevo_estado == Orden.Estado.CANCELADO:
        for d in orden.detalles.order_by('sector_id'):
            Sector.objects.filter(pk=d.sector_id).update(stock=F('stock') + d.cantidad)

    orden.estado = nuevo_estado
    orden.save(update_fields=['estado', 'actualizada'])
    return orden
