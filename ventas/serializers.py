from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from .models import Carro, DetalleOrden, ItemCarro, Orden, Ticket


# ------------------------------------------------------------------- entrada
class AgregarItemSerializer(serializers.Serializer):
    sector = serializers.IntegerField(min_value=1)
    cantidad = serializers.IntegerField(min_value=1, max_value=settings.MAX_TICKETS_POR_COMPRA)


class ActualizarItemSerializer(serializers.Serializer):
    cantidad = serializers.IntegerField(min_value=1, max_value=settings.MAX_TICKETS_POR_COMPRA)


class CambiarEstadoSerializer(serializers.Serializer):
    # El organizador solo puede mover a estos dos estados
    estado = serializers.ChoiceField(choices=[Orden.Estado.CANCELADO, Orden.Estado.ENTREGADO])


# --------------------------------------------------------------------- carro
class ItemCarroSerializer(serializers.ModelSerializer):
    sector_nombre = serializers.CharField(source='sector.nombre', read_only=True)
    precio_unitario = serializers.DecimalField(source='sector.precio', max_digits=10,
                                               decimal_places=2, read_only=True)
    subtotal = serializers.SerializerMethodField()
    reserva_activa = serializers.BooleanField(read_only=True)
    segundos_restantes = serializers.SerializerMethodField()

    class Meta:
        model = ItemCarro
        fields = ('id', 'sector', 'sector_nombre', 'cantidad', 'precio_unitario', 'subtotal',
                  'expira_en', 'reserva_activa', 'segundos_restantes')

    def get_subtotal(self, obj):
        return obj.sector.precio * obj.cantidad

    def get_segundos_restantes(self, obj):
        return max(int((obj.expira_en - timezone.now()).total_seconds()), 0)


class CarroSerializer(serializers.ModelSerializer):
    items = ItemCarroSerializer(many=True, read_only=True)
    evento_titulo = serializers.SerializerMethodField()
    total_tickets = serializers.SerializerMethodField()
    total_precio = serializers.SerializerMethodField()
    max_tickets = serializers.SerializerMethodField()

    class Meta:
        model = Carro
        fields = ('id', 'evento', 'evento_titulo', 'items', 'total_tickets', 'total_precio',
                  'max_tickets')

    def get_evento_titulo(self, obj):
        return obj.evento.titulo if obj.evento else None

    def get_total_tickets(self, obj):
        return sum(i.cantidad for i in obj.items.all())

    def get_total_precio(self, obj):
        return sum(i.sector.precio * i.cantidad for i in obj.items.all())

    def get_max_tickets(self, obj):
        return settings.MAX_TICKETS_POR_COMPRA


# -------------------------------------------------------------------- órdenes
class DetalleOrdenSerializer(serializers.ModelSerializer):
    sector_nombre = serializers.CharField(source='sector.nombre', read_only=True)

    class Meta:
        model = DetalleOrden
        fields = ('id', 'sector', 'sector_nombre', 'cantidad', 'precio_unitario')


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

    class Meta:
        model = Ticket
        fields = ('id', 'codigo', 'orden', 'orden_estado', 'evento', 'evento_titulo',
                  'sector_nombre', 'creado')
