from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Message  # Cambiado de Mensaje a Message


@receiver(post_save, sender=Message)
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

    # 👁️ Observador 1: Actualizar la conversación (Conversation)
    # Tu modelo Conversation calcula el último mensaje mediante get_last_message()
    # y guarda automáticamente updated_at, por lo que basta con guardar la conversación.
    conversacion = mensaje.conversation
    conversacion.save()  # Actualiza automáticamente updated_at en Conversation

    # 👁️ Observador 2: Disparar notificación push o WebSocket/MQTT a los participantes
    # Obtenemos los destinatarios excluyendo al emisor del mensaje (sender)
    destinatarios = conversacion.participants.exclude(id=mensaje.sender.id)

    # for destinatario in destinatarios:
    #     notificar_cliente_mqtt(destinatario, mensaje)