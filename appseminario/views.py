import json
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.urls import reverse  # <-- AGREGÁ ESTA LÍNEA AL PRINCIPIO DE TODO

from .models import UserProfile, Conversation, Message, Contact, Llamada

def search_users_api(request):
    """
    Busca usuarios en la plataforma por nombre de contacto o número de teléfono.
    """
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'status': 'success', 'results': []})

    current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]

    # 1. Buscar en contactos guardados del usuario actual
    user_contacts = Contact.objects.filter(
        user=current_user
    ).filter(
        Q(name__icontains=query) | Q(phone_number__icontains=query)
    )

    results = []
    found_phones = set()

    for contact in user_contacts:
        results.append({
            'name': contact.name or contact.phone_number,
            'phone_number': contact.phone_number,
            'is_saved': True
        })
        found_phones.add(contact.phone_number)

    # 2. Buscar usuarios registrados en la plataforma que NO estén en contactos pero coincidan
    other_users = User.objects.filter(
        username__icontains=query
    ).exclude(username=current_user.username)

    for u in other_users:
        if u.username not in found_phones:
            results.append({
                'name': u.username,
                'phone_number': u.username,
                'is_saved': False
            })

    return JsonResponse({'status': 'success', 'results': results})

# ==========================================
# 1. PANTALLAS PRINCIPALES (HTML Render)
# ==========================================

def home(request):
    if request.user.is_authenticated:
        current_user = request.user
    else:
        current_user, _ = User.objects.get_or_create(username="invitado")

    # Obtener únicamente los contactos visibles marcados para el Home
    contacts = Contact.objects.filter(user=current_user, visible_in_home=True)

    contacts_data = []
    for c in contacts:
        display_name = c.name.strip() if (c.name and c.name.strip()) else f"Contacto {c.phone_number}"
        
        contacts_data.append({
            'id': c.id,
            'contact_id': c.id,
            'name': display_name,
            'phone_number': c.phone_number,
        })

    return render(request, 'home.html', {'contacts': contacts_data})


def chat_detail(request, room_id=None, username=None):
    """
    Muestra la sala de chat e inyecta la Clave Pública del destinatario para Libsodium.
    """
    current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]
    
    if room_id:
        conversation = get_object_or_404(Conversation, id=room_id)
    elif username:
        other_user = get_object_or_404(User, username=username)
        conversation = Conversation.objects.filter(is_group=False, participants=current_user).filter(participants=other_user).first()
        if not conversation:
            conversation = Conversation.objects.create(is_group=False)
            conversation.participants.add(current_user, other_user)

    # Identificar al otro participante para extraer su clave pública y su información de contacto
    other_participant = conversation.participants.exclude(id=current_user.id).first()
    display_name = "Chat"
    contacto_pub_key = ""

    if conversation.is_group:
        display_name = conversation.name or "Grupo sin nombre"
    elif other_participant:
        contact = Contact.objects.filter(user=current_user, phone_number=other_participant.username).first()
        display_name = contact.name if (contact and contact.name) else other_participant.username
        
        # Recuperamos u obtenemos el perfil criptográfico del destinatario
        other_profile, _ = UserProfile.objects.get_or_create(user=other_participant)
        contacto_pub_key = other_profile.pub_key or ""

    messages = conversation.messages.order_by('timestamp')

    return render(request, 'chat.html', {
        'conversation': conversation,
        'messages': messages,
        'display_name': display_name,
        'contacto_pub_key': contacto_pub_key  # <-- Clave pública inyectada para encriptar en el HTML
    })


@csrf_exempt
def hide_chat_from_home_api(request, contact_id):
    """
    Oculta el contacto de home.html sin borrar la conversación ni eliminarlo de la lista de contactos.
    """
    if request.method == 'POST':
        current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]
        contact = get_object_or_404(Contact, id=contact_id, user=current_user)
        
        contact.visible_in_home = False
        contact.save()
        
        return JsonResponse({'status': 'success', 'message': 'Contacto quitado del Inicio'})
    
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)


def chat(request):
    """Redirige al chat resolviendo la conversación según el parámetro ?to=NUMERO."""
    phone = request.GET.get('to')
    if phone:
        target_user, _ = User.objects.get_or_create(username=phone)
        UserProfile.objects.get_or_create(user=target_user)

        current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]

        conversation = Conversation.objects.filter(
            is_group=False,
            participants=current_user
        ).filter(participants=target_user).first()

        if not conversation:
            conversation = Conversation.objects.create(is_group=False, created_by=current_user)
            conversation.participants.add(current_user, target_user)

        return redirect('chat_detail', room_id=conversation.id)

    return redirect('home')


def newchat(request):
    current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]
    contacts = Contact.objects.filter(user=current_user)
    return render(request, 'newchat.html', {'contacts': contacts})


def call(request):
    recent_calls = []
    if request.user.is_authenticated:
        recent_calls = (Llamada.objects.filter(emisor=request.user) | 
                        Llamada.objects.filter(receptor_principal=request.user)).order_by('-fecha_inicio')
    return render(request, 'call.html', {'calls': recent_calls})


def call_room(request, room_id):
    call_obj = get_object_or_404(Llamada, id=room_id)
    return render(request, 'call_room.html', {'call': call_obj})


def profile(request):
    prof = getattr(request.user, 'profile', None) if request.user.is_authenticated else None
    return render(request, 'profile.html', {'profile': prof})


@csrf_exempt  # <-- AGREGAR ESTO AQUÍ para evitar el error 403 Forbidden en el Onboarding
def onboard(request):
    """
    Inicia sesión de usuario usando su número telefónico y almacena su clave pública de Libsodium.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            phone = data.get('phone', '').strip()
            public_key = data.get('public_key', '').strip()

            if phone:
                user, _ = User.objects.get_or_create(username=phone)
                
                profile, _ = UserProfile.objects.get_or_create(user=user)
                if public_key:
                    profile.pub_key = public_key
                    profile.save()
                
                login(request, user)
                return JsonResponse({'status': 'success', 'redirect_url': reverse('home')})
            
            return JsonResponse({'status': 'error', 'message': 'Teléfono requerido'}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'JSON Inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Error interno: {str(e)}'}, status=500)

    return render(request, 'onboard.html')



@csrf_exempt
def actualizar_clave_publica_api(request):
    """
    Endpoint de respaldo (POST) por si se requiere actualizar la clave pública desde home.html de forma aislada.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            public_key = data.get('public_key', '').strip()
            
            current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]
            profile, _ = UserProfile.objects.get_or_create(user=current_user)
            
            profile.pub_key = public_key
            profile.save()
            return JsonResponse({'status': 'success', 'message': 'Clave criptográfica sincronizada.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
            
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)


# ==========================================
# 2. MODALES / ACCIONES ASÍNCRONAS
# ==========================================

@require_POST
def modal_handler(request, modal_type):
    try:
        data = json.loads(request.body.decode('utf-8'))
        current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]

        # A) Crear o Editar Contacto
        if modal_type == 'mContact':
            contact_id = data.get('cId')
            name = data.get('cName', '').strip()
            phone = data.get('cNum', '').strip()

            if not name or not phone:
                return JsonResponse({'status': 'error', 'message': 'Nombre y número son obligatorios.'}, status=400)

            target_user, _ = User.objects.get_or_create(username=phone)

            if contact_id:
                contact = Contact.objects.filter(id=contact_id, user=current_user).first()
                if contact:
                    contact.name = name
                    contact.phone_number = phone
                    contact.contact = target_user
                    contact.save()
                    return JsonResponse({'status': 'success', 'message': 'Contacto actualizado con éxito.'})
                else:
                    return JsonResponse({'status': 'error', 'message': 'Contacto no encontrado.'}, status=404)
            else:
                Contact.objects.create(
                    user=current_user,
                    contact=target_user,
                    name=name,
                    phone_number=phone
                )
                return JsonResponse({'status': 'success', 'message': 'Contacto creado con éxito.'})
                
        return JsonResponse({'status': 'error', 'message': 'Tipo de modal no reconocido.'}, status=400)

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Error en el servidor: {str(e)}'}, status=500)

@csrf_exempt  # Permite que la API reciba datos asíncronos por fetch
def send_message_api(request):
    """
    Recibe el payload del mensaje encriptado desde el frontend y lo guarda en la BD.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            conversation_id = data.get('conversation_id')
            # 'content' guardará el texto cifrado Base64 generado por sodium.js
            encrypted_content = data.get('content', '').strip() 

            if not conversation_id or not encrypted_content:
                return JsonResponse({'status': 'error', 'message': 'Faltan parámetros obligatorios.'}, status=400)

            # Buscar la conversación
            conversation = get_object_or_404(Conversation, id=conversation_id)

            # Identificar el usuario emisor real (o usar invitado de respaldo si no está autenticado)
            current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]

            # Crear y almacenar el mensaje con el contenido cifrado de Libsodium
            nuevo_mensaje = Message.objects.create(
                conversation=conversation,
                sender=current_user,
                content=encrypted_content,
                msg_type='text'
            )

            # Actualizar la fecha de modificación de la conversación para que suba en el Home
            conversation.save()

            return JsonResponse({
                'status': 'success', 
                'message': 'Mensaje cifrado guardado correctamente.',
                'message_id': nuevo_mensaje.id,
                'timestamp': nuevo_mensaje.timestamp.strftime('%H:%M')
            })

        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'JSON Inválido.'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Error en el servidor: {str(e)}'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)

@csrf_exempt
def delete_message_api(request, message_id):
    """
    Elimina un mensaje de la base de datos de forma permanente (ideal para el modo Blindado).
    """
    if request.method == 'POST':
        try:
            # Buscamos el mensaje por su ID
            mensaje = get_object_or_404(Message, id=message_id)
            
            # Verificación de seguridad básica: solo el emisor puede mandar a borrar su mensaje
            current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]
            
            # Si prefieres que cualquiera en el chat pueda borrarlo para ambos lados (como un chat secreto),
            # puedes quitar o comentar esta validación de emisor:
            if mensaje.sender != current_user and current_user.username != "invitado":
                return JsonResponse({'status': 'error', 'message': 'No tienes permisos para borrar este mensaje.'}, status=403)
            
            # Borramos el registro físico de la base de datos de Django
            mensaje.delete()
            
            return JsonResponse({'status': 'success', 'message': 'Mensaje eliminado del servidor sin dejar rastros.'})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Error en el servidor: {str(e)}'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)
