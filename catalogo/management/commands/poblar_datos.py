"""
Borra los datos de catálogo y ventas y carga datos nuevos, con sectores
NUMERADOS (filas x asientos) para poder elegir asientos.

Uso:
    python manage.py poblar_datos                # borra y vuelve a cargar todo
    python manage.py poblar_datos --sin-ventas   # sin órdenes de ejemplo

Qué borra: Tickets, Órdenes, Carros, Asientos, Sectores, Eventos y Recintos.
Qué NO borra: tu superusuario ni otros usuarios que hayas creado.
Qué crea: organizador1, organizador2, espectador1, espectador2 (clave: demo12345).
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Usuario
from catalogo.models import Asiento, Evento, Recinto, Sector
from ventas.models import Carro, DetalleOrden, ItemCarro, Orden, Ticket
from ventas.services import pagar_orden

CLAVE = 'demo12345'

# (nombre, dirección, ciudad, capacidad)
RECINTOS = [
    ('Arena Central', 'Av. Principal 123', 'Santiago', 15000),
    ('Teatro Municipal', 'Calle Teatro 456', 'Santiago', 1200),
    ('Estadio Sur', 'Av. Deportes 789', 'Valparaíso', 30000),
]

# Cada sector: (nombre, precio, filas, asientos_por_fila)
#   filas > 0 y asientos_por_fila > 0  -> sector NUMERADO (el stock se calcula solo)
#   filas = 0 y asientos_por_fila = 0  -> sector GENERAL (se usa `stock`)
# Evento: (titulo, artista, categoria, descripcion, dias_desde_hoy, recinto_idx, organizador_idx, sectores)
EVENTOS = [
    ('Gira Mundial 2026', 'Banda Demo', Evento.Categoria.CONCIERTO,
     'Concierto de rock con toda la producción.', 30, 0, 0,
     [('Cancha VIP', 90000, 4, 10, 0),
      ('Cancha General', 60000, 0, 0, 200),
      ('Galería', 30000, 6, 12, 0)]),
    ('Noche de Teatro', 'Compañía Demo', Evento.Categoria.TEATRO,
     'Obra clásica en versión contemporánea.', 45, 1, 1,
     [('Platea', 25000, 8, 10, 0),
      ('Balcón', 15000, 5, 10, 0)]),
    ('Festival de Verano', 'Varios Artistas', Evento.Categoria.FESTIVAL,
     'Dos escenarios y más de diez bandas.', 60, 2, 0,
     [('Pase Premium', 75000, 3, 8, 0),
      ('Pase General', 35000, 0, 0, 500)]),
    ('Clásico del Fútbol', 'Selección Demo', Evento.Categoria.DEPORTE,
     'Partido amistoso internacional.', 20, 2, 1,
     [('Tribuna Norte', 20000, 6, 15, 0),
      ('Tribuna Sur', 20000, 6, 15, 0),
      ('Palco', 80000, 2, 6, 0)]),
    ('Noche de Jazz', 'Cuarteto Demo', Evento.Categoria.CONCIERTO,
     'Jazz en vivo en formato íntimo.', 15, 1, 0,
     [('Mesa Frontal', 40000, 3, 8, 0),
      ('Sala', 22000, 6, 10, 0)]),
]


class Command(BaseCommand):
    help = 'Borra catálogo y ventas y los repuebla con datos nuevos (con asientos numerados).'

    def add_arguments(self, parser):
        parser.add_argument('--sin-ventas', action='store_true',
                            help='No crear órdenes de ejemplo (el panel de estadísticas quedará vacío).')

    @transaction.atomic
    def handle(self, *args, **options):
        self._limpiar()
        usuarios = self._usuarios()
        eventos = self._catalogo(usuarios['orgs'])
        if not options['sin_ventas']:
            self._ventas(usuarios['esps'], eventos)
        self._resumen(usuarios)

    # ------------------------------------------------------------ limpieza
    def _limpiar(self):
        """Orden importante: primero lo que depende de otras tablas (hay FKs PROTECT)."""
        Ticket.objects.all().delete()
        DetalleOrden.objects.all().delete()
        Orden.objects.all().delete()
        ItemCarro.objects.all().delete()
        Carro.objects.all().delete()
        Asiento.objects.all().delete()
        Sector.objects.all().delete()
        Evento.objects.all().delete()
        Recinto.objects.all().delete()
        self.stdout.write('Datos anteriores eliminados.')

    # ------------------------------------------------------------ usuarios
    def _usuario(self, username, rol):
        user, _ = Usuario.objects.get_or_create(
            username=username, defaults={'rol': rol, 'email': f'{username}@demo.cl'})
        user.rol = rol
        user.set_password(CLAVE)       # se resetea la clave por si la habías cambiado
        user.save()
        return user

    def _usuarios(self):
        return {
            'orgs': [self._usuario('organizador1', Usuario.Rol.ORGANIZADOR),
                     self._usuario('organizador2', Usuario.Rol.ORGANIZADOR)],
            'esps': [self._usuario('espectador1', Usuario.Rol.ESPECTADOR),
                     self._usuario('espectador2', Usuario.Rol.ESPECTADOR)],
        }

    # ------------------------------------------------------------ catálogo
    def _catalogo(self, orgs):
        recintos = [Recinto.objects.create(nombre=n, direccion=d, ciudad=c, capacidad=cap)
                    for n, d, c, cap in RECINTOS]
        ahora = timezone.now().replace(hour=21, minute=0, second=0, microsecond=0)
        eventos = []
        for titulo, artista, cat, desc, dias, r_idx, o_idx, sectores in EVENTOS:
            evento = Evento.objects.create(
                organizador=orgs[o_idx], recinto=recintos[r_idx], titulo=titulo, artista=artista,
                categoria=cat, descripcion=desc, fecha_inicio=ahora + timedelta(days=dias))
            for nombre, precio, filas, cols, stock in sectores:
                numerado = filas > 0 and cols > 0
                sector = Sector.objects.create(
                    evento=evento, nombre=nombre, precio=precio, filas=filas, asientos_por_fila=cols,
                    stock=filas * cols if numerado else stock)   # numerado: stock = filas x columnas
                if numerado:
                    sector.generar_asientos()                    # <- esto era lo que faltaba
            eventos.append(evento)
        return eventos

    # ------------------------------------------------------------ ventas de ejemplo
    def _ventas(self, esps, eventos):
        """
        Crea algunas compras pagadas usando pagar_orden() (la misma lógica real):
        descuenta stock, genera tickets con UUID y deja asientos como VENDIDOS.
        """
        plan = [  # (espectador, evento_idx, sector_nombre, cantidad)
            (0, 0, 'Cancha VIP', 3),
            (0, 1, 'Platea', 2),
            (1, 0, 'Cancha General', 4),
            (1, 3, 'Tribuna Norte', 5),
            (1, 4, 'Mesa Frontal', 2),
        ]
        for e_idx, ev_idx, sector_nombre, cantidad in plan:
            evento = eventos[ev_idx]
            sector = evento.sectores.get(nombre=sector_nombre)
            orden = Orden.objects.create(usuario=esps[e_idx], evento=evento,
                                         estado=Orden.Estado.PENDIENTE,
                                         total=sector.precio * cantidad)
            detalle = DetalleOrden.objects.create(orden=orden, sector=sector, cantidad=cantidad,
                                                  precio_unitario=sector.precio)
            if sector.con_asientos:
                # Primeros asientos del sector (A1, A2...), para que el mapa muestre ocupados
                detalle.asientos.set(list(sector.asientos.all()[:cantidad]))
            pagar_orden(orden)

    # ------------------------------------------------------------ resumen
    def _resumen(self, usuarios):
        self.stdout.write(self.style.SUCCESS(
            f'Listo: {Recinto.objects.count()} recintos, {Evento.objects.count()} eventos, '
            f'{Sector.objects.count()} sectores, {Asiento.objects.count()} asientos, '
            f'{Orden.objects.count()} órdenes.'))
        self.stdout.write(f'Usuarios (clave {CLAVE}): organizador1, organizador2, '
                          f'espectador1, espectador2')
