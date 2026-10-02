"""Usuario personalizado: hereda de AbstractUser y agrega el campo `rol`."""
from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    # CHOICES del rol: base del control de acceso (RBAC) de toda la API
    class Rol(models.TextChoices):
        ESPECTADOR = 'ESPECTADOR', 'Espectador'
        ORGANIZADOR = 'ORGANIZADOR', 'Organizador de Eventos'

    rol = models.CharField(max_length=15, choices=Rol.choices, default=Rol.ESPECTADOR)

    def __str__(self):
        return f'{self.username} ({self.get_rol_display()})'
