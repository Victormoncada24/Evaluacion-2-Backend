from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Evento, Recinto, Sector


class RecintoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recinto
        fields = '__all__'


class SectorSerializer(serializers.ModelSerializer):
    disponibles = serializers.SerializerMethodField()

    class Meta:
        model = Sector
        fields = ('id', 'evento', 'nombre', 'precio', 'stock', 'disponibles')

    @extend_schema_field(serializers.IntegerField())
    def get_disponibles(self, obj):
        # `disponibles` viene de con_disponibilidad(); si no, usamos el stock
        return getattr(obj, 'disponibles', obj.stock)

    def validate_evento(self, evento):
        """Un organizador solo puede crear/editar sectores de SUS eventos."""
        request = self.context.get('request')
        if request and evento.organizador_id != request.user.id:
            raise serializers.ValidationError('Solo puedes gestionar sectores de tus eventos.')
        if self.instance and self.instance.evento_id != evento.id:
            raise serializers.ValidationError('No se puede mover un sector a otro evento.')
        return evento


class EventoSerializer(serializers.ModelSerializer):
    organizador = serializers.ReadOnlyField(source='organizador.username')
    recinto_detalle = RecintoSerializer(source='recinto', read_only=True)
    categoria_display = serializers.CharField(source='get_categoria_display', read_only=True)
    sectores = SectorSerializer(many=True, read_only=True)

    class Meta:
        model = Evento
        fields = ('id', 'titulo', 'artista', 'categoria', 'categoria_display', 'descripcion',
                  'fecha_inicio', 'activo', 'organizador', 'recinto', 'recinto_detalle',
                  'sectores')

    def validate_fecha_inicio(self, valor):
        if self.instance is None and valor <= timezone.now():
            raise serializers.ValidationError('La fecha del evento debe ser futura.')
        return valor
