from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

urlpatterns = [
    # ---- Público
    path('', views.home, name='home'),
    path('eventos/<int:pk>/', views.evento_detalle, name='evento_detalle'),
    # ---- Cuenta
    path('registro/', views.registro, name='registro'),
    path('login/', LoginView.as_view(template_name='login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    # ---- Compra (espectador): usan los mismos servicios que la API
    path('eventos/<int:pk>/agregar/', views.agregar_al_carro, name='agregar_al_carro'),
    path('carro/', views.carro, name='carro'),
    path('carro/quitar/<int:item_id>/', views.quitar_del_carro, name='quitar_del_carro'),
    path('carro/vaciar/', views.vaciar_el_carro, name='vaciar_carro'),
    path('carro/pagar/', views.pagar_carro, name='pagar_carro'),
    path('mis-entradas/', views.mis_entradas, name='mis_entradas'),
    # ---- Administrador
    path('panel/', views.dashboard, name='dashboard'),
]
