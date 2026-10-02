from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Usuario


class TokenConRolSerializer(TokenObtainPairSerializer):
    """
    Login JWT con CLAIMS PERSONALIZADOS: el payload del token incluye `rol`
    y `username`, de modo que el cliente sabe qué mostrar sin otra consulta.
    (La API igual valida el rol contra la BD: el claim es informativo.)
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['rol'] = user.rol
        token['username'] = user.username
        return token

    def validate(self, attrs):
        data = super().validate(attrs)   # genera access + refresh
        data['rol'] = self.user.rol      # también lo devolvemos en el cuerpo
        return data


class RegistroSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = Usuario
        fields = ('id', 'username', 'email', 'password', 'rol')

    def create(self, validated_data):
        # create_user hashea la contraseña (nunca se guarda en texto plano)
        return Usuario.objects.create_user(**validated_data)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
