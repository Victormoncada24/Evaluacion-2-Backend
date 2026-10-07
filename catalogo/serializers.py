from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from django.db import transaction
from rest_framework import serializers

from .models import Evento, Recinto, Sector


class RecintoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recinto
        fields = '__all__'


class SectorSerializer(serializers.ModelSerializer):
    disponibles = serializers.SerializerMethodField()
    con_asientos = serializers.BooleanField(read_only=True)

    class Meta:
        model = Sector
        fields = ('id', 'evento', 'nombre', 'precio', 'stock', 'filas', 'asientos_por_fila',
                  'con_asientos', 'disponibles')
        extra_kwargs = {'stock': {'required': False}}   # en sectores numerados se calcula solo

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

    def validate(self, attrs):
        actual = self.instance
        filas = attrs.get('filas', actual.filas if actual else 0)
        columnas = attrs.get('asientos_por_fila', actual.asientos_por_fila if actual else 0)
        if actual:
            # Cambiar el mapa de asientos de un sector ya creado dejaria tickets huerfanos
            if filas != actual.filas or columnas != actual.asientos_por_fila:
                raise serializers.ValidationError('No se puede cambiar las filas/asientos de un sector ya creado.')
            if actual.con_asientos and 'stock' in attrs and attrs['stock'] != actual.stock:
                raise serializers.ValidationError('El stock de un sector con asientos se calcula solo.')
            return attrs
        if (filas > 0) != (columnas > 0):
            raise serializers.ValidationError('Para asientos numerados indica filas y asientos por fila (ambos).')
        if filas > 0:
            attrs['stock'] = filas * columnas           # stock = cantidad de asientos
        elif 'stock' not in attrs:
            raise serializers.ValidationError({'stock': 'Este campo es requerido.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        sector = super().create(validated_data)
        if sector.con_asientos:
            sector.generar_asientos()
        return sector


class AsientoMapaSerializer(serializers.Serializer):
    """Solo describe la respuesta de /api/sectores/{id}/asientos/ para Swagger."""
    id = serializers.IntegerField()
    fila = serializers.CharField()
    numero = serializers.IntegerField()
    etiqueta = serializers.CharField()
    estado = serializers.ChoiceField(choices=['LIBRE', 'RESERVADO', 'VENDIDO', 'EN_TU_CARRO'])


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
