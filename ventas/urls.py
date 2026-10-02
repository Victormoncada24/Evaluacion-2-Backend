from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register('mis-ordenes', views.MisOrdenesViewSet, basename='mis-ordenes')
router.register('organizador/ordenes', views.OrdenesOrganizadorViewSet, basename='organizador-ordenes')

urlpatterns = [
    path('carro/', views.CarroView.as_view(), name='carro'),
    path('carro/items/', views.CarroItemsView.as_view(), name='carro-items'),
    path('carro/items/<int:pk>/', views.CarroItemDetalleView.as_view(), name='carro-item'),
    path('carro/checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('mis-entradas/', views.MisEntradasView.as_view(), name='mis-entradas'),
] + router.urls
