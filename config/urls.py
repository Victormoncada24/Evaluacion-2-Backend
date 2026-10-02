"""
Enrutamiento principal.
  /                  -> inicio público (panel)
  /panel/            -> dashboard del administrador
  /api/auth/...      -> registro, login JWT, refresh, logout
  /api/...           -> catálogo, carro, órdenes
  /api/docs/         -> Swagger (SOLO administrador)
  cualquier otra URL -> 404 personalizado con re_path
"""
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAdminUser

from panel import views as panel_views
from panel.decorators import solo_admin

# Swagger y el esquema OpenAPI: el admin entra con su sesión (login HTML).
# `solo_admin` redirige al login si no hay sesión y da 403 si no es staff.
schema_view = SpectacularAPIView.as_view(
    authentication_classes=[SessionAuthentication], permission_classes=[IsAdminUser])
swagger_view = SpectacularSwaggerView.as_view(
    url_name='schema', authentication_classes=[SessionAuthentication],
    permission_classes=[IsAdminUser])

urlpatterns = [
    path('', include('panel.urls')),
    path('api/auth/', include('accounts.urls')),
    path('api/', include('catalogo.urls')),
    path('api/', include('ventas.urls')),
    path('api/schema/', solo_admin(schema_view), name='schema'),
    path('api/docs/', solo_admin(swagger_view), name='swagger-ui'),
    # SIEMPRE al final: atrapa toda ruta no reconocida y muestra el 404 propio,
    # incluso con DEBUG=True (donde Django mostraría su página técnica).
    re_path(r'^.*$', panel_views.pagina_no_encontrada),
]

handler404 = 'panel.views.pagina_no_encontrada'
