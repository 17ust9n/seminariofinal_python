from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Mensaje  # Tu modelo de Mensajes

@receiver(post_save, sender=Mensaje)
def ejecutar_observadores_de_mensaje(sender, instance, created, **kwargs):
    """
    Observer de Mensajería: Se ejecuta automáticamente
    CADA VEZ que un usuario envía/guarda un Mensaje.
    """
    if created:
        # Ejecuta la notificación una vez confirmada la transacción en la base de datos
        transaction.on_commit(lambda: notificar_nuevo_mensaje(instance))

def notificar_nuevo_mensaje(mensaje):
    """Acciones automatizadas al recibir un mensaje nuevo."""
    
    # 👁️ Observador 1: Actualizar el contador/estado del chat
    chat = mensaje.chat
    chat.ultimo_mensaje = mensaje.contenido
    chat.fecha_ultimo_mensaje = mensaje.creado_en
    chat.save()

    # 👁️ Observador 2: Disparar notificación push o WebSocket/MQTT si aplica
    # (Ejemplo: notificar al destinatario)
    destinatario = mensaje.receptor
    # notificar_cliente_mqtt(destinatario, mensaje)
