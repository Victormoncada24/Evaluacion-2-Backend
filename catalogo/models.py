"""
Catálogo: Recinto -> Evento -> Sector (localidad con precio y stock).
Integridad referencial: PROTECT impide borrar algo que ya tiene ventas/eventos.
"""
import string

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone


class Recinto(models.Model):
    nombre = models.CharField(max_length=120)
    direccion = models.CharField(max_length=200)
    ciudad = models.CharField(max_length=80)
    capacidad = models.PositiveIntegerField()

    def __str__(self):
        return f'{self.nombre} ({self.ciudad})'


class Evento(models.Model):
    # CHOICES de categoría: alimenta filtros y "categoría que más se vende"
    class Categoria(models.TextChoices):
        CONCIERTO = 'CONCIERTO', 'Concierto'
        FESTIVAL = 'FESTIVAL', 'Festival'
        TEATRO = 'TEATRO', 'Teatro'
        DEPORTE = 'DEPORTE', 'Deporte'
        OTRO = 'OTRO', 'Otro'

    organizador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='eventos')
    recinto = models.ForeignKey(Recinto, on_delete=models.PROTECT, related_name='eventos')
    titulo = models.CharField(max_length=150)
    artista = models.CharField(max_length=120)
    categoria = models.CharField(max_length=15, choices=Categoria.choices,
                                 default=Categoria.CONCIERTO)
    descripcion = models.TextField(blank=True)
    fecha_inicio = models.DateTimeField()
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['fecha_inicio']

    def __str__(self):
        return self.titulo


class SectorQuerySet(models.QuerySet):
    def con_disponibilidad(self):
        """
        Agrega dos columnas calculadas en SQL:
          reservados  = tickets retenidos en carros cuya reserva AÚN no expira
          disponibles = stock - reservados   (lo que otro usuario puede elegir)
        El stock real solo baja al pagar; las reservas solo "bloquean" mientras
        no vence el temporizador.
        """
        ahora = timezone.now()
        return self.annotate(
            reservados=Coalesce(
                Sum('items_carro__cantidad',
                    filter=Q(items_carro__expira_en__gt=ahora),
                    output_field=IntegerField()),
                Value(0)),
        ).annotate(
            disponibles=Greatest(F('stock') - F('reservados'), Value(0)),
        )


class Sector(models.Model):
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name='sectores')
    nombre = models.CharField(max_length=80)
    precio = models.DecimalField(max_digits=10, decimal_places=2,
                                 validators=[MinValueValidator(0)])
    stock = models.PositiveIntegerField()   # entradas realmente libres (sin contar reservas)
    # Asientos numerados (OPCIONAL). Si ambos valores son > 0, el sector tiene mapa de asientos
    # y el stock se calcula solo (filas x asientos por fila). Con 0 es un sector general.
    filas = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(26)])
    asientos_por_fila = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(50)])

    objects = SectorQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['evento', 'nombre'], name='sector_unico_por_evento'),
        ]

    def __str__(self):
        return f'{self.nombre} - {self.evento.titulo}'

    @property
    def con_asientos(self):
        return self.filas > 0 and self.asientos_por_fila > 0

    def generar_asientos(self):
        """Crea los asientos del sector: filas A, B, C... y numeros 1..N en cada fila."""
        letras = string.ascii_uppercase
        Asiento.objects.bulk_create([
            Asiento(sector=self, fila=letras[f], numero=n)
            for f in range(self.filas) for n in range(1, self.asientos_por_fila + 1)])


class Asiento(models.Model):
    """
    Un asiento fisico de un sector numerado. No guarda si esta libre u ocupado:
    eso se deduce de los tickets pagados y de las reservas vigentes del carro
    (asi cancelar una orden libera el asiento sin tocar esta tabla).
    """
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE, related_name='asientos')
    fila = models.CharField(max_length=2)        # 'A'..'Z' (maximo 26 filas, por eso ordena bien)
    numero = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['fila', 'numero']
        constraints = [
            models.UniqueConstraint(fields=['sector', 'fila', 'numero'], name='asiento_unico_por_sector'),
        ]

    @property
    def codigo(self):
        return f'{self.fila}{self.numero}'          # ej: C7

    @property
    def etiqueta(self):
        return f'Fila {self.fila} · Asiento {self.numero}'

    def __str__(self):
        return f'{self.codigo} ({self.sector})'
