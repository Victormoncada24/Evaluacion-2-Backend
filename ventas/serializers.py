from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Carro, DetalleOrden, ItemCarro, Orden, Ticket

MAX = settings.MAX_TICKETS_POR_COMPRA


# ------------------------------------------------------------------- entrada
class AgregarItemSerializer(serializers.Serializer):
    """Sector general: envía `cantidad`. Sector numerado: envía `asientos` (lista de ids)."""
    sector = serializers.IntegerField(min_value=1)
    cantidad = serializers.IntegerField(min_value=1, max_value=MAX, required=False)
    asientos = serializers.ListField(child=serializers.IntegerField(min_value=1),
                                     required=False, allow_empty=False, max_length=MAX)

    def validate(self, attrs):
        if 'cantidad' not in attrs and 'asientos' not in attrs:
            raise serializers.ValidationError('Indica la cantidad (sector general) o los asientos (sector numerado).')
        return attrs


class ActualizarItemSerializer(serializers.Serializer):
    cantidad = serializers.IntegerField(min_value=1, max_value=MAX, required=False)
    asientos = serializers.ListField(child=serializers.IntegerField(min_value=1),
                                     required=False, max_length=MAX)   # lista vacía = quitar

    def validate(self, attrs):
        if 'cantidad' not in attrs and 'asientos' not in attrs:
            raise serializers.ValidationError('Indica la nueva cantidad o la lista de asientos.')
        return attrs


class CambiarEstadoSerializer(serializers.Serializer):
    # El organizador solo puede mover a estos dos estados
    estado = serializers.ChoiceField(choices=[Orden.Estado.CANCELADO, Orden.Estado.ENTREGADO])


# --------------------------------------------------------------------- carro
class ItemCarroSerializer(serializers.ModelSerializer):
    sector_nombre = serializers.CharField(source='sector.nombre', read_only=True)
    evento = serializers.IntegerField(source='sector.evento_id', read_only=True)
    evento_titulo = serializers.CharField(source='sector.evento.titulo', read_only=True)
    precio_unitario = serializers.DecimalField(source='sector.precio', max_digits=10,
                                               decimal_places=2, read_only=True)
    subtotal = serializers.SerializerMethodField()
    reserva_activa = serializers.BooleanField(read_only=True)
    segundos_restantes = serializers.SerializerMethodField()
    asientos = serializers.SerializerMethodField()

    class Meta:
        model = ItemCarro
        fields = ('id', 'sector', 'sector_nombre', 'evento', 'evento_titulo', 'cantidad',
                  'asientos', 'precio_unitario', 'subtotal', 'expira_en', 'reserva_activa',
                  'segundos_restantes')

    def get_subtotal(self, obj):
        return obj.sector.precio * obj.cantidad

    def get_segundos_restantes(self, obj):
        return max(int((obj.expira_en - timezone.now()).total_seconds()), 0)

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_asientos(self, obj):
        return [a.etiqueta for a in obj.asientos.all()]


class CarroSerializer(serializers.ModelSerializer):
    items = ItemCarroSerializer(many=True, read_only=True)
    total_tickets = serializers.SerializerMethodField()
    total_precio = serializers.SerializerMethodField()
    max_tickets = serializers.SerializerMethodField()

    class Meta:
        model = Carro
        fields = ('id', 'items', 'total_tickets', 'total_precio', 'max_tickets')

    def get_total_tickets(self, obj):
        return sum(i.cantidad for i in obj.items.all())

    def get_total_precio(self, obj):
        return sum(i.sector.precio * i.cantidad for i in obj.items.all())

    def get_max_tickets(self, obj):
        return MAX


# -------------------------------------------------------------------- órdenes
class DetalleOrdenSerializer(serializers.ModelSerializer):
    sector_nombre = serializers.CharField(source='sector.nombre', read_only=True)
    asientos = serializers.SerializerMethodField()

    class Meta:
        model = DetalleOrden
        fields = ('id', 'sector', 'sector_nombre', 'cantidad', 'asientos', 'precio_unitario')

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_asientos(self, obj):
        return [a.etiqueta for a in obj.asientos.all()]


class OrdenSerializer(serializers.ModelSerializer):
    usuario = serializers.ReadOnlyField(source='usuario.username')
    evento_titulo = serializers.CharField(source='evento.titulo', read_only=True)
    detalles = DetalleOrdenSerializer(many=True, read_only=True)
    codigos_tickets = serializers.SerializerMethodField()

    class Meta:
        model = Orden
        fields = ('id', 'usuario', 'evento', 'evento_titulo', 'estado', 'total', 'creada',
                  'actualizada', 'detalles', 'codigos_tickets')

    def get_codigos_tickets(self, obj):
        return [str(t.codigo) for t in obj.tickets.all()]


class TicketSerializer(serializers.ModelSerializer):
    orden_estado = serializers.CharField(source='orden.estado', read_only=True)
    evento = serializers.IntegerField(source='orden.evento_id', read_only=True)
    evento_titulo = serializers.CharField(source='orden.evento.titulo', read_only=True)
    sector_nombre = serializers.CharField(source='detalle.sector.nombre', read_only=True)
    asiento = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = ('id', 'codigo', 'orden', 'orden_estado', 'evento', 'evento_titulo',
                  'sector_nombre', 'asiento', 'creado')

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_asiento(self, obj):
        return obj.asiento.etiqueta if obj.asiento_id else None
