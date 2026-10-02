"""Carga datos de ejemplo: python manage.py cargar_demo"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Usuario
from catalogo.models import Evento, Recinto, Sector


class Command(BaseCommand):
    help = 'Crea un organizador, un espectador, un recinto y dos eventos con sectores.'

    def handle(self, *args, **options):
        org, creado = Usuario.objects.get_or_create(
            username='organizador1', defaults={'rol': Usuario.Rol.ORGANIZADOR, 'email': 'org@demo.cl'})
        if creado:
            org.set_password('demo12345')
            org.save()
        esp, creado = Usuario.objects.get_or_create(
            username='espectador1', defaults={'rol': Usuario.Rol.ESPECTADOR, 'email': 'esp@demo.cl'})
        if creado:
            esp.set_password('demo12345')
            esp.save()

        recinto, _ = Recinto.objects.get_or_create(
            nombre='Arena Central', defaults={'direccion': 'Av. Principal 123', 'ciudad': 'Santiago', 'capacidad': 15000})

        ahora = timezone.now()
        datos = [
            ('Gira Mundial 2026', 'Banda Demo', Evento.Categoria.CONCIERTO, 30,
             [('Cancha VIP', 90000, 50), ('Cancha General', 60000, 200), ('Galería', 30000, 400)]),
            ('Noche de Teatro', 'Compañía Demo', Evento.Categoria.TEATRO, 45,
             [('Platea', 25000, 100), ('Balcón', 15000, 80)]),
        ]
        for titulo, artista, categoria, dias, sectores in datos:
            evento, _ = Evento.objects.get_or_create(
                titulo=titulo, organizador=org,
                defaults={'artista': artista, 'categoria': categoria, 'recinto': recinto,
                          'fecha_inicio': ahora + timedelta(days=dias)})
            for nombre, precio, stock in sectores:
                Sector.objects.get_or_create(evento=evento, nombre=nombre,
                                             defaults={'precio': precio, 'stock': stock})

        self.stdout.write(self.style.SUCCESS(
            'Listo. Usuarios: organizador1 / espectador1 (clave: demo12345).'))
