from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import EsEspectador, EsOrganizador

from . import services
from .filters import OrdenFilter, TicketFilter
from .models import ItemCarro, Orden, Ticket
from .serializers import (ActualizarItemSerializer, AgregarItemSerializer, CambiarEstadoSerializer,
                          CarroSerializer, OrdenSerializer, TicketSerializer)


def _ordenes_base():
    """Consulta con joins/prefetch para no hacer una query por cada orden."""
    return (Orden.objects.select_related('evento', 'usuario')
            .prefetch_related('detalles__sector', 'detalles__asientos', 'tickets'))


# ============================================================ CARRO (Espectador)
@extend_schema(tags=['Carro'])
class CarroTicketsView(APIView):
    """GET/POST/DELETE /api/carro-tickets/ (según la matriz de roles de la pauta)."""
    permission_classes = [EsEspectador]

    @extend_schema(responses=CarroSerializer)
    def get(self, request):
        """Mi carro persistente (con tiempo restante de cada reserva)."""
        carro = services.obtener_carro(request.user)
        return Response(CarroSerializer(carro).data)

    @extend_schema(request=AgregarItemSerializer, responses={201: CarroSerializer})
    def post(self, request):
        """
        Agrega entradas y las RESERVA (inicia el temporizador). Sector general: {"sector": 1, "cantidad": 2}.
        Sector numerado: {"sector": 3, "asientos": [41, 42]} (ids de /api/sectores/3/asientos/).
        """
        ser = AgregarItemSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        datos = ser.validated_data
        if 'asientos' in datos:        # sector numerado: asientos concretos
            carro = services.fijar_asientos(request.user, datos['sector'], datos['asientos'], sumar=True)
        else:                          # sector general: cantidad
            carro = services.fijar_cantidad(request.user, datos['sector'], datos['cantidad'], sumar=True)
        return Response(CarroSerializer(carro).data, status=201)

    @extend_schema(responses=CarroSerializer)
    def delete(self, request):
        """Vacía todo el carro y libera todas sus reservas."""
        return Response(CarroSerializer(services.vaciar_carro(request.user)).data)


@extend_schema(tags=['Carro'])
class CarroItemDetalleView(APIView):
    """PATCH/DELETE /api/carro-tickets/{id}/ -> modificar o quitar UN ítem."""
    permission_classes = [EsEspectador]

    @extend_schema(request=ActualizarItemSerializer, responses=CarroSerializer)
    def patch(self, request, pk):
        """Cambia la cantidad de un ítem de mi carro."""
        ser = ActualizarItemSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        item = get_object_or_404(ItemCarro, pk=pk, carro__usuario=request.user)  # solo MI carro
        datos = ser.validated_data
        if 'asientos' in datos:        # reemplaza la lista de asientos del sector (vacía = quitar)
            carro = services.fijar_asientos(request.user, item.sector_id, datos['asientos'])
        else:
            carro = services.fijar_cantidad(request.user, item.sector_id, datos['cantidad'])
        return Response(CarroSerializer(carro).data)

    @extend_schema(responses=CarroSerializer)
    def delete(self, request, pk):
        """Quita un ítem y libera su reserva."""
        carro = services.quitar_item(request.user, pk)
        return Response(CarroSerializer(carro).data)


@extend_schema(tags=['Compras'])
class PagarView(APIView):
    """POST /api/compras/pagar/ -> checkout + pago."""
    permission_classes = [EsEspectador]

    @extend_schema(request=None, responses={201: OrdenSerializer(many=True)})
    def post(self, request):
        """
        Paga el carro: valida stock, lo descuenta, crea la orden (una por evento)
        y genera un ticket con UUID único por cada entrada.
        """
        ordenes = services.hacer_checkout(request.user)
        ids = [o.pk for o in ordenes]
        return Response(OrdenSerializer(_ordenes_base().filter(pk__in=ids), many=True).data, status=201)


# ========================================================= ESPECTADOR: historial
@extend_schema(tags=['Espectador'])
class MisOrdenesViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrdenSerializer
    permission_classes = [EsEspectador]
    filterset_class = OrdenFilter
    ordering_fields = ['creada', 'total']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Orden.objects.none()
        return _ordenes_base().filter(usuario=self.request.user)


@extend_schema(tags=['Espectador'])
class MisEntradasView(ListAPIView):
    """Mis tickets válidos (órdenes PAGADO o ENTREGADO; las canceladas no aparecen)."""
    serializer_class = TicketSerializer
    permission_classes = [EsEspectador]
    filterset_class = TicketFilter

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Ticket.objects.none()
        return (Ticket.objects
                .filter(orden__usuario=self.request.user, orden__estado__in=Orden.ESTADOS_CON_VENTA)
                .select_related('orden__evento', 'detalle__sector', 'asiento').order_by('-creado'))


# ======================================================= ORGANIZADOR: órdenes
@extend_schema(tags=['Compras'])
class ComprasOrganizadorViewSet(viewsets.ReadOnlyModelViewSet):
    """ORGANIZADOR: consulta las ventas de MIS eventos y cambia su estado (CANCELADO / ENTREGADO)."""
    serializer_class = OrdenSerializer
    permission_classes = [EsOrganizador]
    filterset_class = OrdenFilter
    ordering_fields = ['creada', 'total']
    lookup_value_regex = r'\d+'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Orden.objects.none()
        return _ordenes_base().filter(evento__organizador=self.request.user)

    @extend_schema(request=CambiarEstadoSerializer, responses=OrdenSerializer)
    @action(detail=True, methods=['patch'], url_path='estado')
    def estado(self, request, pk=None):
        """CANCELADO repone el stock (si estaba pagada); ENTREGADO cierra la orden."""
        ser = CambiarEstadoSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        orden = services.cambiar_estado_orden(pk, ser.validated_data['estado'], request.user)
        return Response(OrdenSerializer(_ordenes_base().get(pk=orden.pk)).data)
