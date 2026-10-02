from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import LogoutView, RegistroView, TokenView

urlpatterns = [
    path('registro/', RegistroView.as_view(), name='registro'),
    path('token/', TokenView.as_view(), name='token_obtain'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout_api'),
]
