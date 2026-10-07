"""
Permisos RBAC (control de acceso por rol).
Cada clase responde: "¿este usuario tiene el rol necesario para esta vista?".
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Usuario


def _rol(request):
    """Devuelve el rol del usuario autenticado o None si es anónimo."""
    user = request.user
    return user.rol if user and user.is_authenticated else None


class EsEspectador(BasePermission):
    """Carro, checkout, mis órdenes y mis entradas."""
    message = 'Solo los espectadores pueden usar el carro y comprar entradas.'

    def has_permission(self, request, view):
        # Los administradores (is_staff) gestionan la plataforma: no compran ni tienen carro
        return _rol(request) == Usuario.Rol.ESPECTADOR and not request.user.is_staff


class EsOrganizador(BasePermission):
    """Gestión de eventos y cambio de estado de órdenes."""
    message = 'Esta acción es exclusiva de organizadores de eventos.'

    def has_permission(self, request, view):
        return _rol(request) == Usuario.Rol.ORGANIZADOR


class SoloLecturaOOrganizador(BasePermission):
    """Catálogo público: GET/HEAD/OPTIONS libres; escribir exige ser organizador."""
    message = 'Solo los organizadores pueden modificar el catálogo.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return _rol(request) == Usuario.Rol.ORGANIZADOR


class EsDuenoDelEvento(BasePermission):
    """
    Permiso a nivel de OBJETO: un organizador solo modifica lo que es suyo.
    Funciona con Evento (obj.organizador) y con Sector (obj.evento.organizador).
    """
    message = 'No eres el organizador de este evento.'

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        evento = getattr(obj, 'evento', obj)
        return evento.organizador_id == request.user.id
