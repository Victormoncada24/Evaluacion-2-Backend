"""Rutas tal como las define la matriz de roles del Proyecto 3 (EVA-2)."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register('mis-ordenes', views.MisOrdenesViewSet, basename='mis-ordenes')
# GET /api/compras/ (ventas del organizador), GET /api/compras/{id}/, PATCH /api/compras/{id}/estado/
router.register('compras', views.ComprasOrganizadorViewSet, basename='compras')

urlpatterns = [
    path('carro-tickets/', views.CarroTicketsView.as_view(), name='carro-tickets'),
    path('carro-tickets/<int:pk>/', views.CarroItemDetalleView.as_view(), name='carro-ticket-item'),
    path('compras/pagar/', views.PagarView.as_view(), name='compras-pagar'),
    path('mis-entradas/', views.MisEntradasView.as_view(), name='mis-entradas'),
] + router.urls
