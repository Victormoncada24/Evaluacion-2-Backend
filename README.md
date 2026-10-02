# EVA-2 · Proyecto 3 — Venta de Entradas para Eventos y Conciertos

Django REST Framework + PostgreSQL + JWT (SimpleJWT) + django-filter + drf-spectacular.

## Puesta en marcha
```bash
python -m venv .venv      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # completa BD y datos del alumno
# Crear la BD en PostgreSQL:  CREATE DATABASE boletaje;
python manage.py makemigrations accounts catalogo ventas   # accounts primero (usuario propio)
python manage.py migrate
python manage.py createsuperuser                      # este es el "administrador"
python manage.py cargar_demo                          # opcional: datos de ejemplo
python manage.py runserver
```
- Inicio público: http://localhost:8000/
- Login (sesión): http://localhost:8000/login/ → Dashboard `/panel/` y Swagger `/api/docs/` (solo staff)

## Matriz de roles
| Recurso | Público | Espectador | Organizador | Admin (staff) |
|---|---|---|---|---|
| GET recintos / eventos / sectores | ✔ | ✔ | ✔ | ✔ |
| POST/PUT/PATCH/DELETE catálogo | ✘ | ✘ | ✔ (solo lo suyo) | – |
| /api/carro/*, checkout, mis-ordenes, mis-entradas | ✘ | ✔ | ✘ | – |
| /api/organizador/ordenes/ + PATCH …/estado/ | ✘ | ✘ | ✔ (solo sus eventos) | – |
| /panel/ y /api/docs/ | ✘ | ✘ | ✘ | ✔ |

## Prueba rápida con curl
```bash
# 1) Login (devuelve access, refresh y rol)
curl -X POST localhost:8000/api/auth/token/ -H "Content-Type: application/json" \
     -d '{"username":"espectador1","password":"demo12345"}'
# 2) Reservar 2 entradas del sector 1
curl -X POST localhost:8000/api/carro/items/ -H "Authorization: Bearer <ACCESS>" \
     -H "Content-Type: application/json" -d '{"sector":1,"cantidad":2}'
# 3) Pagar
curl -X POST localhost:8000/api/carro/checkout/ -H "Authorization: Bearer <ACCESS>"
# 4) Organizador cancela (repone stock)
curl -X PATCH localhost:8000/api/organizador/ordenes/1/estado/ -H "Authorization: Bearer <ACCESS_ORG>" \
     -H "Content-Type: application/json" -d '{"estado":"CANCELADO"}'
```
Filtros: `/api/eventos/?artista=banda&fecha_desde=2026-11-01&precio_min=20000&precio_max=90000&sector=vip`
