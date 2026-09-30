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

    # 1. Obtener los contactos visibles marcados para el Home
    contacts = Contact.objects.filter(user=current_user, visible_in_home=True)

    contacts_data = []
    for c in contacts:
        display_name = c.name.strip() if (c.name and c.name.strip()) else f"Contacto {c.phone_number}"
        
        contacts_data.append({
            'id': c.id,
            'is_group': False,
            'name': display_name,
            'phone_number': c.phone_number,
        })

    # 2. INTRODUCCIÓN CRÍTICA: Obtener las conversaciones grupales del usuario
    groups = Conversation.objects.filter(is_group=True, participants=current_user)
    for g in groups:
        contacts_data.append({
            'id': f"group-{g.id}", # ID seguro para el DOM
            'is_group': True,
            'name': g.name or "Grupo sin nombre",
            'phone_number': f"Sala {g.id}", # Texto auxiliar descriptivo
            'room_id': g.id
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

    # Identificar al otro participante
    other_participant = conversation.participants.exclude(id=current_user.id).first()
    
    # 1. Intentamos leer el nombre desde la URL (?name=...)
    url_name = request.GET.get('name', '').strip()
    display_name = url_name if url_name else ""
    contacto_pub_key = ""

    if conversation.is_group:
        display_name = conversation.name or "Grupo sin nombre"
    elif other_participant:
        # 2. Si no vino por URL o está vacío, buscamos de forma inteligente en Contactos
        if not display_name or display_name == "Chat":
            # Buscamos cualquier contacto de este usuario cuyo número coincida con el username del otro
            contact = Contact.objects.filter(user=current_user, phone_number=other_participant.username).first()
            
            if contact and contact.name:
                display_name = contact.name
            else:
                # 3. Si no está agendado, mostramos su teléfono/nombre de usuario en vez de la palabra "Chat"
                display_name = other_participant.username 
        
        # Recuperamos el perfil criptográfico
        other_profile, _ = UserProfile.objects.get_or_create(user=other_participant)
        contacto_pub_key = other_profile.pub_key or ""

    messages = conversation.messages.order_by('timestamp')

    return render(request, 'chat.html', {
        'conversation': conversation,
        'messages': messages,
        'display_name': display_name,
        'recipient_public_key': contacto_pub_key,  
        'is_group': conversation.is_group,
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
    name = request.GET.get('name', '') # 👈 1. Capturamos el nombre que viene desde el frontend

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

        # 👈 2. Modificamos el redireccionamiento para incluir el nombre en los parámetros GET
        from django.urls import reverse
        url_destino = reverse('chat_detail', kwargs={'room_id': conversation.id})
        if name:
            url_destino += f"?name={name}"
            
        return redirect(url_destino)

    return redirect('home')



def newchat(request):
    if request.user.is_authenticated:
        current_user = request.user
    else:
        current_user, _ = User.objects.get_or_create(username="invitado")
        
    # Obtener los contactos individuales del usuario
    contacts = Contact.objects.filter(user=current_user)
    
    # Obtener los grupos en los que participa el usuario
    groups = Conversation.objects.filter(is_group=True, participants=current_user)
    
    return render(request, 'newchat.html', {
        'contacts': contacts,
        'groups': groups
    })



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


# ==========================================
# 2. NUEVOS ENDPOINTS ASÍNCRONOS PROTEGIDOS
# ==========================================

@csrf_exempt
@require_POST
def create_group_api(request):
    """
    Crea un nuevo grupo de forma persistente y asíncrona sin interferir con la sesión.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        group_name = data.get('name', '').strip()
        participant_phones = data.get('participants', [])

        if not group_name:
            return JsonResponse({'status': 'error', 'message': 'El nombre del grupo es obligatorio.'}, status=400)

        if request.user.is_authenticated:
            current_user = request.user
        else:
            current_user, _ = User.objects.get_or_create(username="invitado")

        # Generar conversación persistente de tipo grupal
        conversation = Conversation.objects.create(
            is_group=True,
            name=group_name,
            created_by=current_user
        )
        
        # El creador ingresa como primer participante
        conversation.participants.add(current_user)

        # Asociar a los miembros restantes marcados
        for phone in participant_phones:
            user_to_add = User.objects.filter(username=phone).first()
            if user_to_add:
                conversation.participants.add(user_to_add)

        return JsonResponse({
            'status': 'success', 
            'message': 'Grupo registrado de forma persistente.',
            'room_id': conversation.id
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Estructura JSON inválida.'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Falla interna: {str(e)}'}, status=500)


@csrf_exempt
@require_POST
def edit_group_api(request, group_id):
    """
    Modifica el nombre de una conversación grupal.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        new_name = data.get('name', '').strip()
        
        if not new_name:
            return JsonResponse({'status': 'error', 'message': 'El nombre no puede estar vacío.'}, status=400)
            
        group = get_object_or_404(Conversation, id=group_id, is_group=True)
        group.name = new_name
        group.save()
        
        return JsonResponse({'status': 'success', 'message': 'Nombre del grupo actualizado.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_POST
def delete_group_api(request, group_id):
    """
    Elimina por completo la conversación grupal de la plataforma.
    """
    try:
        group = get_object_or_404(Conversation, id=group_id, is_group=True)
        group.delete()
        return JsonResponse({'status': 'success', 'message': 'Grupo eliminado correctamente.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_POST
def actualizar_clave_publica_api(request):
    """
    Sincroniza la clave Libsodium sin alterar el estado de autenticación del usuario.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        pub_key_base64 = data.get('public_key', '').strip()

        if not pub_key_base64:
            return JsonResponse({'status': 'error', 'message': 'Clave pública vacía.'}, status=400)

        if request.user.is_authenticated:
            current_user = request.user
        else:
            current_user, _ = User.objects.get_or_create(username="invitado")

        profile_obj, _ = UserProfile.objects.get_or_create(user=current_user)
        profile_obj.pub_key = pub_key_base64
        profile_obj.save()

        return JsonResponse({'status': 'success', 'message': 'Llave guardada en Django de forma segura.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
def onboard(request):
    """
    Maneja el Onboarding de usuarios.
    Si es POST: Inicia sesión usando su número telefónico y almacena su clave de Libsodium.
    Si es GET: Renderiza la pantalla visual de Onboarding.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            phone = data.get('phone', '').strip()
            public_key = data.get('public_key', '').strip()

            if phone:
                user, _ = User.objects.get_or_create(username=phone)
                
                profile_obj, _ = UserProfile.objects.get_or_create(user=user)
                if public_key:
                    profile_obj.pub_key = public_key
                    profile_obj.save()
                
                login(request, user)
                return JsonResponse({'status': 'success', 'redirect_url': reverse('home')})
            
            return JsonResponse({'status': 'error', 'message': 'Teléfono requerido.'}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'JSON Inválido.'}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Error interno: {str(e)}'}, status=500)

    # 🔄 SOLUCCIÓN AL ERROR: Si es un GET (carga inicial), renderiza la pantalla de login/onboard
    # Cambia 'onboard.html' por el nombre real de tu archivo de onboarding si es distinto
    return render(request, 'onboard.html')



# ==========================================
# 3. MODALES / ACCIONES ASÍNCRONAS
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



@require_POST
def delete_contact_api(request, contact_id):
    """
    Elimina un contacto guardado por el usuario actual.
    """
    try:
        current_user = (
            request.user
            if request.user.is_authenticated
            else User.objects.get_or_create(username="invitado")[0]
        )

        contact = Contact.objects.filter(
            id=contact_id,
            user=current_user
        ).first()

        if not contact:
            return JsonResponse({
                'status': 'error',
                'message': 'Contacto no encontrado.'
            }, status=404)

        contact.delete()

        return JsonResponse({
            'status': 'success',
            'message': 'Contacto eliminado correctamente.'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)