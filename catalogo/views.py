from django.db.models import Prefetch, ProtectedError
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.permissions import EsDuenoDelEvento, EsOrganizador, SoloLecturaOOrganizador

from .filters import EventoFilter, SectorFilter
from .models import Evento, Recinto, Sector
from .serializers import EventoSerializer, RecintoSerializer, SectorSerializer


class ProtegidoMixin:
    """Si algo no se puede borrar por tener datos asociados (PROTECT) -> 409, no 500."""

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response({'detail': 'No se puede eliminar: tiene datos asociados.'}, status=409)


@extend_schema(tags=['Catálogo'])
class RecintoViewSet(ProtegidoMixin, viewsets.ModelViewSet):
    """Público: listar/ver. Organizador: crear/editar/eliminar."""
    queryset = Recinto.objects.all()
    serializer_class = RecintoSerializer
    permission_classes = [SoloLecturaOOrganizador]
    filterset_fields = ['ciudad']
    search_fields = ['nombre', 'ciudad']


@extend_schema(tags=['Catálogo'])
class EventoViewSet(ProtegidoMixin, viewsets.ModelViewSet):
    """
    Público: catálogo de eventos ACTIVOS (con filtros y búsqueda).
    Organizador: crea eventos y solo edita/elimina los SUYOS.
    """
    serializer_class = EventoSerializer
    permission_classes = [SoloLecturaOOrganizador, EsDuenoDelEvento]
    filterset_class = EventoFilter
    search_fields = ['titulo', 'artista', 'recinto__nombre', 'recinto__ciudad']
    ordering_fields = ['fecha_inicio', 'titulo']
    ordering = ['fecha_inicio']

    def get_queryset(self):
        qs = (Evento.objects.select_related('recinto', 'organizador')
              .prefetch_related(Prefetch('sectores', queryset=Sector.objects.con_disponibilidad())))
        if getattr(self, 'swagger_fake_view', False):   # generación del esquema OpenAPI
            return qs.none()
        if self.action in ('list', 'retrieve', 'sectores'):
            return qs.filter(activo=True)               # lo que ve el público
        return qs.filter(organizador=self.request.user)  # escritura: solo lo propio

    def perform_create(self, serializer):
        # El organizador sale del token, nunca del cuerpo de la petición
        serializer.save(organizador=self.request.user)

    @extend_schema(responses=SectorSerializer(many=True))
    @action(detail=True, methods=['get'], url_path='sectores', permission_classes=[AllowAny])
    def sectores(self, request, pk=None):
        """PÚBLICO: sectores del evento con precio y entradas disponibles (acepta los filtros de sectores)."""
        evento = self.get_object()
        qs = Sector.objects.filter(evento=evento).con_disponibilidad().order_by('precio')
        qs = SectorFilter(request.query_params, queryset=qs).qs
        return Response(SectorSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'], url_path='mis-eventos', permission_classes=[EsOrganizador])
    def mis_eventos(self, request):
        """Todos mis eventos (activos o no), con los mismos filtros."""
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)


@extend_schema(tags=['Catálogo'])
class SectorViewSet(ProtegidoMixin, viewsets.ModelViewSet):
    """Público: sectores con precio y entradas disponibles. Organizador: gestiona los suyos."""
    serializer_class = SectorSerializer
    permission_classes = [SoloLecturaOOrganizador, EsDuenoDelEvento]
    filterset_class = SectorFilter
    search_fields = ['nombre', 'evento__titulo']
    ordering_fields = ['precio', 'nombre']

    def get_queryset(self):
        qs = Sector.objects.select_related('evento').con_disponibilidad()
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()
        if self.action in ('list', 'retrieve'):
            return qs.filter(evento__activo=True)
        return qs.filter(evento__organizador=self.request.user)
