from django.conf import settings
from django.db.models import Sum

from accounts.models import Usuario
from ventas.models import ItemCarro


def datos_alumno(request):
    """
    Variables disponibles en TODOS los templates:
      ALUMNO          -> datos del footer
      CARRO_CANTIDAD  -> tickets en el carro del espectador (globito de la barra superior)
    """
    contexto = {'ALUMNO': settings.ALUMNO, 'CARRO_CANTIDAD': 0}
    user = request.user
    if user.is_authenticated and user.rol == Usuario.Rol.ESPECTADOR:
        contexto['CARRO_CANTIDAD'] = (
            ItemCarro.objects.filter(carro__usuario=user).aggregate(t=Sum('cantidad'))['t'] or 0)
    return contexto
