"""
Ventas: Carro (1:1 con Usuario) -> ItemCarro, y Orden -> DetalleOrden -> Ticket.

Idea central para la defensa:
  * El CARRO vive en PostgreSQL, por eso sobrevive a logout y a otro dispositivo.
  * La ORDEN es el historial: se crea al pagar y nunca se borra.
  * El STOCK del sector solo baja cuando la orden pasa a PAGADO.
"""
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Carro(models.Model):
    # OneToOne: cada usuario tiene exactamente UN carro activo y persistente
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='carro')
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Carro de {self.usuario}'


class ItemCarro(models.Model):
    # El carro puede mezclar sectores de DISTINTOS eventos (lo pide la pauta)
    carro = models.ForeignKey(Carro, on_delete=models.CASCADE, related_name='items')
    sector = models.ForeignKey('catalogo.Sector', on_delete=models.CASCADE,
                               related_name='items_carro')
    cantidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    # Solo para sectores numerados: los asientos elegidos (cantidad == asientos.count())
    asientos = models.ManyToManyField('catalogo.Asiento', blank=True, related_name='items_carro')
    # Temporizador: mientras expira_en > ahora, estos tickets están RESERVADOS
    expira_en = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['carro', 'sector'], name='unico_sector_por_carro'),
        ]

    @property
    def reserva_activa(self):
        return self.expira_en > timezone.now()


class Orden(models.Model):
    # CHOICES de estados de la transacción
    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        PAGADO = 'PAGADO', 'Pagado'
        CANCELADO = 'CANCELADO', 'Cancelado'
        ENTREGADO = 'ENTREGADO', 'Entregado'

    # Estados que cuentan como "venta real" (estadísticas y mis entradas)
    ESTADOS_CON_VENTA = (Estado.PAGADO, Estado.ENTREGADO)

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                related_name='ordenes')
    evento = models.ForeignKey('catalogo.Evento', on_delete=models.PROTECT,
                               related_name='ordenes')
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE,
                              db_index=True)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-creada']

    def __str__(self):
        return f'Orden #{self.pk} - {self.estado}'


class DetalleOrden(models.Model):
    orden = models.ForeignKey(Orden, on_delete=models.CASCADE, related_name='detalles')
    sector = models.ForeignKey('catalogo.Sector', on_delete=models.PROTECT,
                               related_name='detalles_orden')
    cantidad = models.PositiveIntegerField()
    # Se guarda el precio del momento: si el organizador lo cambia, el historial no se altera
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    # Asientos comprados (solo sectores numerados)
    asientos = models.ManyToManyField('catalogo.Asiento', blank=True, related_name='detalles_orden')


class Ticket(models.Model):
    orden = models.ForeignKey(Orden, on_delete=models.CASCADE, related_name='tickets')
    detalle = models.ForeignKey(DetalleOrden, on_delete=models.CASCADE, related_name='tickets')
    # Asiento asignado (None en sectores generales). PROTECT: no se borra un asiento ya vendido.
    asiento = models.ForeignKey('catalogo.Asiento', null=True, blank=True, on_delete=models.PROTECT,
                                related_name='tickets')
    # UUID único e imposible de adivinar: es el código de la entrada
    codigo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    creado = models.DateTimeField(auto_now_add=True)
