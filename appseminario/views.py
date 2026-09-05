import json
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.urls import reverse

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
        'contacto_pub_key': contacto_pub_key
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


@csrf_exempt
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


@csrf_exempt
def send_message_api(request):
    """
    Recibe el payload del mensaje encriptado desde el frontend y lo guarda en la BD.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            conversation_id = data.get('conversation_id')
            encrypted_content = data.get('content', '').strip() 

            if not conversation_id or not encrypted_content:
                return JsonResponse({'status': 'error', 'message': 'Faltan parámetros obligatorios.'}, status=400)

            conversation = get_object_or_404(Conversation, id=conversation_id)
            current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]

            nuevo_mensaje = Message.objects.create(
                conversation=conversation,
                sender=current_user,
                content=encrypted_content,
                msg_type='text'
            )

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
    Elimina un mensaje de la base de datos de forma permanente.
    """
    if request.method == 'POST':
        try:
            mensaje = get_object_or_404(Message, id=message_id)
            current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]
            
            if mensaje.sender != current_user and current_user.username != "invitado":
                return JsonResponse({'status': 'error', 'message': 'No tienes permisos para borrar este mensaje.'}, status=403)
            
            mensaje.delete()
            return JsonResponse({'status': 'success', 'message': 'Mensaje eliminado del servidor sin dejar rastros.'})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Error en el servidor: {str(e)}'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)


def settings_view(request):
    """
    Renderiza la pantalla de Ajustes y Seguridad.
    """
    current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]
    profile, _ = UserProfile.objects.get_or_create(user=current_user)

    context = {
        'security_level': profile.security_level,
        'pub_key': profile.pub_key or 'No generada',
    }
    return render(request, 'settings.html', context)


@csrf_exempt
def update_security_level_api(request):
    """
    API endpoint para actualizar el nivel de seguridad (Modo Blindado).
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            level = int(data.get('security_level', 0))

            current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]
            profile, _ = UserProfile.objects.get_or_create(user=current_user)
            
            profile.security_level = level
            profile.save()

            return JsonResponse({'status': 'success', 'security_level': profile.security_level})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)


def profile(request):
    """
    Vista del perfil de usuario con datos criptográficos y nivel de seguridad.
    """
    if request.user.is_authenticated:
        current_user = request.user
    else:
        current_user, _ = User.objects.get_or_create(username="invitado")

    user_profile, _ = UserProfile.objects.get_or_create(user=current_user)

    # Formatear el label del nivel de seguridad
    sec_label = "Modo Blindado 🛡️" if user_profile.security_level == 1 else "Modo Normal ⚡"

    # Formatear la vista previa corta de la clave pública
    pub_key = user_profile.pub_key or ""
    if len(pub_key) > 16:
        short_key = f"{pub_key[:8]}...{pub_key[-8:]}"
    else:
        short_key = pub_key or "No disponible"

    context = {
        'user_phone': current_user.username,
        'sec_label': sec_label,
        'pub_key_full': pub_key,
        'pub_key_short': short_key,
        'profile': user_profile,
    }
    return render(request, 'profile.html', context)

def edit_profile(request):
    """
    Vista para editar la información del perfil del usuario.
    """
    if request.user.is_authenticated:
        current_user = request.user
    else:
        current_user, _ = User.objects.get_or_create(username="invitado")

    if request.method == 'POST':
        # Procesar actualización del nombre de usuario o teléfono
        new_username = request.POST.get('username', '').strip()
        if new_username:
            current_user.username = new_username
            current_user.save()
            return redirect('profile')

    return render(request, 'edit_profile.html', {'user': current_user})

def settings(request):
    """
    Vista de Ajustes y Seguridad.
    """
    current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]
    profile, _ = UserProfile.objects.get_or_create(user=current_user)

    context = {
        'security_level': profile.security_level,
        'pub_key': profile.pub_key or 'No generada',
    }
    return render(request, 'settings.html', context)


def logout_view(request):
    """
    Cierra la sesión del usuario en Django y destruye las variables de sesión del servidor.
    """
    logout(request)
    return redirect('onboard')

def about(request):
    """
    Renderiza la pantalla 'Acerca de'.
    """
    return render(request, 'about.html')


def terms(request):
    """
    Renderiza la pantalla de 'Términos y Condiciones'.
    """
    return render(request, 'terms.html')