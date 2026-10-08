"""Compatibilidad: ahora cargar_demo delega en poblar_datos (que sí crea asientos)."""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Alias de poblar_datos: borra y recarga los datos de ejemplo con asientos.'

    def handle(self, *args, **options):
        call_command('poblar_datos')
