from rest_framework.routers import SimpleRouter

from .views import EventoViewSet, RecintoViewSet, SectorViewSet

router = SimpleRouter()
router.register('recintos', RecintoViewSet, basename='recinto')
router.register('eventos', EventoViewSet, basename='evento')
router.register('sectores', SectorViewSet, basename='sector')

urlpatterns = router.urls
