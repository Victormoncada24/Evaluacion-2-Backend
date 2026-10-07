"""Formularios HTML del sitio (registro de usuarios)."""
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

from accounts.models import Usuario
from catalogo.models import Evento, Recinto


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


class EventoAdminForm(forms.Form):
    """
    Formulario para que el ADMINISTRADOR cree un evento desde la web.
    Los sectores (nombre, precio, stock) se leen aparte en la vista porque son filas dinámicas.
    El recinto se elige de la lista o se crea uno nuevo escribiendo sus datos.
    """
    titulo = forms.CharField(max_length=150, label='Nombre del evento')
    artista = forms.CharField(max_length=120, label='Artista / banda')
    categoria = forms.ChoiceField(choices=Evento.Categoria.choices, label='Categoría')
    fecha_inicio = forms.DateTimeField(
        label='Fecha y hora', input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'))
    descripcion = forms.CharField(required=False, label='Descripción', widget=forms.Textarea(attrs={'rows': 3}))
    organizador = forms.ModelChoiceField(
        queryset=Usuario.objects.filter(rol=Usuario.Rol.ORGANIZADOR), required=False,
        empty_label='Yo (administrador)', label='Organizador a cargo')
    recinto = forms.ModelChoiceField(
        queryset=Recinto.objects.all(), required=False,
        empty_label='— Crear un recinto nuevo —', label='Recinto')
    # Datos del recinto nuevo (solo si no se elige uno existente)
    recinto_nombre = forms.CharField(required=False, max_length=120, label='Nombre del recinto')
    recinto_direccion = forms.CharField(required=False, max_length=200, label='Dirección')
    recinto_ciudad = forms.CharField(required=False, max_length=80, label='Ciudad')
    recinto_capacidad = forms.IntegerField(required=False, min_value=1, label='Capacidad')

    def clean_fecha_inicio(self):
        fecha = self.cleaned_data['fecha_inicio']
        if fecha <= timezone.now():
            raise forms.ValidationError('La fecha del evento debe ser futura.')
        return fecha

    def clean(self):
        datos = super().clean()
        if not datos.get('recinto'):
            campos = ('recinto_nombre', 'recinto_direccion', 'recinto_ciudad', 'recinto_capacidad')
            if any(not datos.get(c) for c in campos):
                self.add_error('recinto', 'Elige un recinto existente o completa todos los datos del recinto nuevo.')
        return datos
