from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect, render

from accounts.models import Usuario


def solo_admin(vista):
    """
    Restringe una vista al administrador (is_staff).
      - Sin sesión       -> redirige al login propio (/login/?next=...)
      - Con sesión comun -> 403 con template propio
    Se usa en el dashboard y también para proteger Swagger (/api/docs/).
    """
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (request.user.is_active and request.user.is_staff):
            return render(request, '403.html', status=403)
        return vista(request, *args, **kwargs)
    return envoltura


def solo_espectador(vista):
    """
    Las pantallas de compra (carro, pago, mis entradas) son solo para el rol
    ESPECTADOR, igual que en la API (permiso EsEspectador).
      - Sin sesión  -> login y vuelve a la página pedida
      - Otro rol o administrador (is_staff) -> aviso y vuelta al inicio
    """
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if request.user.rol != Usuario.Rol.ESPECTADOR or request.user.is_staff:
            messages.error(request, 'Esta sección es solo para cuentas de espectador.')
            return redirect('home')
        return vista(request, *args, **kwargs)
    return envoltura
