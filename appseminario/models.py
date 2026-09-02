from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    status_text = models.CharField(max_length=100, default="En línea", help_text="Texto corto de estado para #chSub")
    is_online = models.BooleanField(default=False, help_text="Estado del indicador #dot")
    pub_key = models.TextField(blank=True, null=True, help_text="Llave pública para cifrado P2P/MQTT")

    def __str__(self):
        return f"Perfil de {self.user.username}"


class Contact(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contacts_owner')
    contact = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='contacts_added',
        null=True, 
        blank=True,
        help_text="Usuario registrado asociado en la plataforma"
    )
    name = models.CharField(max_length=100, help_text="Nombre local asignado por el usuario (#cName)")
    phone_number = models.CharField(max_length=20, help_text="Número con código de país (#cNum)")
    
    # Campo para ocultar de Home sin borrar el contacto ni las conversaciones
    visible_in_home = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.phone_number}) - Contacto de {self.user.username}"


class Conversation(models.Model):
    name = models.CharField(max_length=100, blank=True, null=True, help_text="Nombre del grupo (#gName) en caso de ser chat grupal")
    is_group = models.BooleanField(default=False)
    participants = models.ManyToManyField(User, related_name='conversations', help_text="Miembros seleccionados (#gPick)")
    
    # LÍNEA CORREGIDA:
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_groups')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def get_last_message(self):
        return self.messages.order_by('-timestamp').first()

    def unread_count_for_user(self, user):
        return self.messages.filter(is_read=False).exclude(sender=user).count()

    def __str__(self):
        if self.is_group:
            return f"Grupo: {self.name or 'Sin Nombre'} (ID: {self.id})"
        return f"Conversación {self.id}"


class Message(models.Model):
    MESSAGE_TYPES = (
        ('text', 'Texto'),
        ('audio', 'Mensaje de Voz'),
    )

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField(blank=True, null=True, help_text="Texto o payload cifrado")
    audio_file = models.FileField(upload_to='chat_audio/', blank=True, null=True)
    msg_type = models.CharField(max_length=10, choices=MESSAGE_TYPES, default='text')
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"Mensaje de {self.sender.username} ({self.timestamp.strftime('%H:%M')})"


class Llamada(models.Model):
    TIPO_CHOICES = [('VO', 'Voz'), ('VI', 'Video')]
    ESTADOS_CHOICES = [('PE', 'Pendiente'), ('CO', 'Contestada'), ('RE', 'Rechazada'), ('FI', 'Finalizada')]

    emisor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='llamadas_iniciadas')
    receptor_principal = models.ForeignKey(User, on_delete=models.CASCADE, related_name='llamadas_recibidas', null=True, blank=True)
    invitados = models.ManyToManyField(User, related_name='llamadas_invitadas', blank=True)
    tipo = models.CharField(max_length=2, choices=TIPO_CHOICES, default='VO')
    estado = models.CharField(max_length=2, choices=ESTADOS_CHOICES, default='PE')
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    duracion_segundos = models.IntegerField(default=0)

    class Meta:
        ordering = ['-fecha_inicio']


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()