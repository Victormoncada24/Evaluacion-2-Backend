"""
Filtros con django-filter. Se usan escribiendo parámetros en la URL, p. ej.:
  /api/eventos/?artista=metallica&fecha_desde=2026-11-01&precio_min=20000&precio_max=90000
  /api/sectores/?evento=3&solo_disponibles=true&precio_max=50000
"""
import django_filters as df

from .models import Evento, Sector


class EventoFilter(df.FilterSet):
    # Rango de fechas (compara solo la parte "fecha" del DateTime)
    fecha_desde = df.DateFilter(field_name='fecha_inicio', lookup_expr='date__gte')
    fecha_hasta = df.DateFilter(field_name='fecha_inicio', lookup_expr='date__lte')
    artista = df.CharFilter(lookup_expr='icontains')
    ciudad = df.CharFilter(field_name='recinto__ciudad', lookup_expr='icontains')
    # Filtros que cruzan la relación con Sector (distinct evita eventos repetidos)
    sector = df.CharFilter(field_name='sectores__nombre', lookup_expr='icontains', distinct=True)
    # RangeFilter genera dos parámetros: precio_min y precio_max
    precio = df.RangeFilter(field_name='sectores__precio', distinct=True)

    class Meta:
        model = Evento
        fields = ['categoria', 'recinto']


class SectorFilter(df.FilterSet):
    nombre = df.CharFilter(lookup_expr='icontains')
    precio = df.RangeFilter()
    solo_disponibles = df.BooleanFilter(method='filtrar_disponibles')

    class Meta:
        model = Sector
        fields = ['evento']

    def filtrar_disponibles(self, queryset, name, value):
        # `disponibles` es la anotación de SectorQuerySet.con_disponibilidad()
        return queryset.filter(disponibles__gt=0) if value else queryset
