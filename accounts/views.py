from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import LogoutSerializer, RegistroSerializer, TokenConRolSerializer


class TokenView(TokenObtainPairView):
    """POST: usuario + contraseña -> access + refresh (con claim `rol`)."""
    serializer_class = TokenConRolSerializer


class RegistroView(generics.CreateAPIView):
    """
    POST público para crear una cuenta.
    NOTA: aquí se permite elegir el rol para poder probar ambos perfiles.
    En producción el rol ORGANIZADOR se asignaría solo por un administrador.
    """
    serializer_class = RegistroSerializer
    permission_classes = [AllowAny]
    authentication_classes = []


class LogoutView(APIView):
    """Invalida el refresh token (lista negra): el token ya no se puede renovar."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LogoutSerializer, responses={205: None})
    def post(self, request):
        ser = LogoutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            RefreshToken(ser.validated_data['refresh']).blacklist()
        except TokenError:
            return Response({'detail': 'Token inválido o ya expirado.'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_205_RESET_CONTENT)
