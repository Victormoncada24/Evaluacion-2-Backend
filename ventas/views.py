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
            .prefetch_related('detalles__sector', 'tickets'))


# ============================================================ CARRO (Espectador)
@extend_schema(tags=['Carro'])
class CarroView(APIView):
    permission_classes = [EsEspectador]

    @extend_schema(responses=CarroSerializer)
    def get(self, request):
        """Mi carro persistente (con tiempo restante de cada reserva)."""
        carro = services.obtener_carro(request.user)
        return Response(CarroSerializer(carro).data)


@extend_schema(tags=['Carro'])
class CarroItemsView(APIView):
    permission_classes = [EsEspectador]

    @extend_schema(request=AgregarItemSerializer, responses={201: CarroSerializer})
    def post(self, request):
        """Agrega entradas de un sector y las RESERVA (inicia el temporizador)."""
        ser = AgregarItemSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        carro = services.fijar_cantidad(request.user, ser.validated_data['sector'],
                                        ser.validated_data['cantidad'], sumar=True)
        return Response(CarroSerializer(carro).data, status=201)


@extend_schema(tags=['Carro'])
class CarroItemDetalleView(APIView):
    permission_classes = [EsEspectador]

    @extend_schema(request=ActualizarItemSerializer, responses=CarroSerializer)
    def patch(self, request, pk):
        """Cambia la cantidad de un ítem de mi carro."""
        ser = ActualizarItemSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        item = get_object_or_404(ItemCarro, pk=pk, carro__usuario=request.user)  # solo MI carro
        carro = services.fijar_cantidad(request.user, item.sector_id, ser.validated_data['cantidad'])
        return Response(CarroSerializer(carro).data)

    @extend_schema(responses=CarroSerializer)
    def delete(self, request, pk):
        """Quita un ítem y libera su reserva."""
        carro = services.quitar_item(request.user, pk)
        return Response(CarroSerializer(carro).data)


@extend_schema(tags=['Carro'])
class CheckoutView(APIView):
    permission_classes = [EsEspectador]

    @extend_schema(request=None, responses={201: OrdenSerializer})
    def post(self, request):
        """Paga el carro: valida stock, lo descuenta, crea la orden y genera tickets UUID."""
        orden = services.hacer_checkout(request.user)
        return Response(OrdenSerializer(_ordenes_base().get(pk=orden.pk)).data, status=201)


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
                .select_related('orden__evento', 'detalle__sector').order_by('-creado'))


# ======================================================= ORGANIZADOR: órdenes
@extend_schema(tags=['Organizador'])
class OrdenesOrganizadorViewSet(viewsets.ReadOnlyModelViewSet):
    """Órdenes de MIS eventos + cambio de estado (CANCELADO / ENTREGADO)."""
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
