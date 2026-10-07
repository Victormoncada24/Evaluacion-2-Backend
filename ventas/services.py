"""
Lógica de negocio del carro y las órdenes (capa de servicios).

Todo lo que toca stock corre dentro de transaction.atomic() y bloquea las filas
con select_for_update(). Eso garantiza que dos compradores simultáneos no
puedan vender la misma última entrada: o se confirma todo, o no se confirma nada.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from catalogo.models import Sector

from .models import Carro, DetalleOrden, ItemCarro, Orden, Ticket

MAX_TICKETS = settings.MAX_TICKETS_POR_COMPRA


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


# ----------------------------------------------------------------------- carro
@transaction.atomic
def fijar_cantidad(usuario, sector_id, cantidad, sumar=False):
    """
    Agrega o modifica un ítem del carro y (re)inicia el temporizador de reserva.
      sumar=True  -> `cantidad` se suma a lo que ya había (POST)
      sumar=False -> `cantidad` pasa a ser el total del sector (PATCH)
    """
    # 1) Bloqueamos el carro del usuario (evita carreras entre dos dispositivos)
    carro = Carro.objects.select_for_update().get(pk=obtener_carro(usuario).pk)

    # 2) Bloqueamos el sector: nadie más reserva/paga este sector hasta terminar
    sector = (Sector.objects.select_for_update(of=('self',)).select_related('evento')
              .filter(pk=sector_id).first())
    if sector is None:
        raise NotFound('El sector no existe.')
    _validar_evento_vendible(sector.evento)

    existente = carro.items.filter(sector=sector).values_list('cantidad', flat=True).first() or 0
    if sumar:
        cantidad += existente

    # 3) Regla: máximo MAX_TICKETS tickets por compra (suma de todo el carro)
    en_otros_sectores = carro.items.exclude(sector=sector).aggregate(t=Sum('cantidad'))['t'] or 0
    if en_otros_sectores + cantidad > MAX_TICKETS:
        raise ValidationError(f'Máximo {MAX_TICKETS} tickets por compra.')

    # 4) Disponibilidad = stock real - reservas vigentes de OTROS usuarios
    disponibles = sector.stock - _reservado_por_otros(sector.id, carro)
    if cantidad > max(disponibles, 0):
        raise ValidationError(f'Solo quedan {max(disponibles, 0)} entradas disponibles en "{sector.nombre}".')

    # 5) Guardamos y reiniciamos el temporizador.
    #    Solo se renuevan los ítems con reserva vigente: uno ya vencido no
    #    "resucita" sin volver a validarse (podría haberlo reservado otra persona).
    ahora = timezone.now()
    nueva_expiracion = ahora + timedelta(minutes=settings.MINUTOS_RESERVA)
    carro.items.filter(expira_en__gt=ahora).update(expira_en=nueva_expiracion)
    ItemCarro.objects.update_or_create(
        carro=carro, sector=sector,
        defaults={'cantidad': cantidad, 'expira_en': nueva_expiracion})
    carro.save(update_fields=['actualizado'])
    return carro


@transaction.atomic
def quitar_item(usuario, item_id):
    carro = Carro.objects.select_for_update().filter(usuario=usuario).first()
    if carro is None:
        raise NotFound('Tu carro está vacío.')
    borrados, _ = carro.items.filter(pk=item_id).delete()
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

    # Validación de stock: real - reservas vigentes de otros compradores.
    # Si falta stock en CUALQUIER ítem, se rechaza todo el pago (rollback).
    for item in items:
        sector = sectores[item.sector_id]
        disponibles = sector.stock - _reservado_por_otros(sector.id, carro)
        if item.cantidad > disponibles:
            raise ValidationError(f'Ya no hay stock suficiente en "{sector.nombre}" (quedan {max(disponibles, 0)}).')

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
        DetalleOrden.objects.bulk_create([
            DetalleOrden(orden=orden, sector=sectores[i.sector_id], cantidad=i.cantidad,
                         precio_unitario=sectores[i.sector_id].precio)
            for i in evento_items])
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
    generan los tickets con UUID.
    """
    if orden.estado != Orden.Estado.PENDIENTE:
        raise ValidationError('Solo se puede pagar una orden pendiente.')

    detalles = list(orden.detalles.all())
    sectores = {s.id: s for s in Sector.objects.select_for_update()
                .filter(pk__in=[d.sector_id for d in detalles]).order_by('pk')}

    # Validación atómica: con las filas bloqueadas, el stock leído es el real
    for d in detalles:
        if sectores[d.sector_id].stock < d.cantidad:
            raise ValidationError(f'Sin stock en "{sectores[d.sector_id].nombre}".')

    for d in detalles:
        sector = sectores[d.sector_id]
        sector.stock -= d.cantidad
        sector.save(update_fields=['stock'])

    # Un Ticket por cada entrada comprada (el UUID se genera solo)
    Ticket.objects.bulk_create([Ticket(orden=orden, detalle=d) for d in detalles for _ in range(d.cantidad)])

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

    # Cancelar una orden PAGADA repone el stock automáticamente.
    # (Una PENDIENTE nunca descontó stock, así que no hay nada que reponer.)
    if orden.estado == Orden.Estado.PAGADO and nuevo_estado == Orden.Estado.CANCELADO:
        for d in orden.detalles.order_by('sector_id'):
            Sector.objects.filter(pk=d.sector_id).update(stock=F('stock') + d.cantidad)

    orden.estado = nuevo_estado
    orden.save(update_fields=['estado', 'actualizada'])
    return orden
