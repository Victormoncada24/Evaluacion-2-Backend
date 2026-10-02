"""Formularios HTML del sitio (registro de usuarios)."""
from django import forms
from django.contrib.auth.forms import UserCreationForm

from accounts.models import Usuario


class RegistroForm(UserCreationForm):
    """
    Registro desde la web. Reutiliza UserCreationForm de Django, que ya valida
    el username único y las reglas de contraseña (AUTH_PASSWORD_VALIDATORS) y
    guarda la clave hasheada. Solo agregamos email y el ROL del usuario.
    """
    email = forms.EmailField(required=True, label='Correo electrónico')
    rol = forms.ChoiceField(choices=Usuario.Rol.choices, initial=Usuario.Rol.ESPECTADOR,
                            widget=forms.RadioSelect, label='¿Cómo usarás Boletaje?')

    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ('username', 'email', 'rol')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Textos de ayuda y placeholders para los inputs
        self.fields['username'].label = 'Usuario'
        self.fields['password1'].label = 'Contraseña'
        self.fields['password2'].label = 'Repite la contraseña'
        self.fields['username'].widget.attrs['placeholder'] = 'tu_usuario'
        self.fields['email'].widget.attrs['placeholder'] = 'correo@ejemplo.cl'
