"""Filtros de órdenes y tickets (django-filter)."""
import django_filters as df

from .models import Orden, Ticket


class OrdenFilter(df.FilterSet):
    fecha_desde = df.DateFilter(field_name='creada', lookup_expr='date__gte')
    fecha_hasta = df.DateFilter(field_name='creada', lookup_expr='date__lte')
    total = df.RangeFilter()   # -> total_min, total_max

    class Meta:
        model = Orden
        fields = ['estado', 'evento']


class TicketFilter(df.FilterSet):
    evento = df.NumberFilter(field_name='orden__evento_id')
    sector = df.NumberFilter(field_name='detalle__sector_id')

    class Meta:
        model = Ticket
        fields = []
