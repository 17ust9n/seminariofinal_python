import json
import traceback
from datetime import timedelta
from django.core.serializers import python
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, request
from django.views.decorators.cache import never_cache
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.utils import timezone

from .models import UserProfile, CallSignal, Conversation, Message, Contact, Llamada


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

@never_cache
def home(request):
    if not request.user.is_authenticated:
        return redirect('onboard')

    current_user = request.user

    # 1. Contactos visibles en el Home
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

    # 2. Grupos del usuario
    groups = Conversation.objects.filter(is_group=True, participants=current_user)
    for g in groups:
        contacts_data.append({
            'id': f"group-{g.id}",
            'is_group': True,
            'name': g.name or "Grupo sin nombre",
            'phone_number': f"Sala {g.id}",
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
            contact = Contact.objects.filter(user=current_user, phone_number=other_participant.username).first()
            if contact and contact.name:
                display_name = contact.name
            else:
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
        'peer_phone': other_participant.username if (other_participant and not conversation.is_group) else '',
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
    name = request.GET.get('name', '') 

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
        
    contacts = Contact.objects.filter(user=current_user)
    groups = Conversation.objects.filter(is_group=True, participants=current_user)
    
    return render(request, 'newchat.html', {
        'contacts': contacts,
        'groups': groups
    })


def call(request):
    """
    Renderiza el historial de llamadas de voz y video del usuario autenticado.
    """
    if not request.user.is_authenticated:
        return redirect('onboard')
        
    recent_calls = Llamada.objects.filter(
        Q(emisor=request.user) | Q(receptor_principal=request.user)
    ).order_by('-fecha_inicio')[:20]

    return render(request, 'call.html', {'recent_calls': recent_calls})


def profile(request):
    """
    Renderiza la vista principal del Perfil levantando datos de seguridad y criptografía.
    """
    phone = request.user.username if request.user.is_authenticated else "Invitado"
    current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]
    profile_obj, _ = UserProfile.objects.get_or_create(user=current_user)
    
    context = {
        'user_phone': phone,
        'sec_label': '🛡️ Blindado' if getattr(profile_obj, 'security_level', 0) == 1 else '🔓 Modo Normal',
        'pub_key_full': getattr(profile_obj, 'pub_key', 'No disponible'),
        'pub_key_short': (getattr(profile_obj, 'pub_key', '')[:14] + '...') if getattr(profile_obj, 'pub_key', '') else 'Sin clave'
    }
    return render(request, 'profile.html', context)


def edit_profile(request):
    """
    Renderiza la pantalla para modificar los datos del perfil local.
    """
    current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]
    profile_obj, _ = UserProfile.objects.get_or_create(user=current_user)

    context = {
        'username': current_user.username,
        'security_level': getattr(profile_obj, 'security_level', 0),
        'pub_key': getattr(profile_obj, 'pub_key', '')
    }
    return render(request, 'edit_profile.html', context)


def settings(request):
    return render(request, 'settings.html')


def about(request):
    return render(request, 'about.html')


def terms(request):
    return render(request, 'terms.html')


# ==========================================
# 2. MODALES Y ACCIONES ASÍNCRONAS (APIs)
# ==========================================

@csrf_exempt
@require_POST
def actualizar_clave_publica_api(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        pub_key_base64 = data.get('public_key', '').strip()

        if not pub_key_base64:
            return JsonResponse({'status': 'error', 'message': 'Clave pública vacía.'}, status=400)

        current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]

        profile_obj, _ = UserProfile.objects.get_or_create(user=current_user)
        profile_obj.pub_key = pub_key_base64
        profile_obj.save()

        return JsonResponse({'status': 'success', 'message': 'Llave guardada en Django de forma segura.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
def onboard(request):
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
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return render(request, 'onboard.html')


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
                return JsonResponse({'status': 'error', 'message': 'Contacto no encontrado.'}, status=404)
            else:
                Contact.objects.create(user=current_user, contact=target_user, name=name, phone_number=phone)
                return JsonResponse({'status': 'success', 'message': 'Contacto creado con éxito.'})
                
        return JsonResponse({'status': 'error', 'message': 'Tipo de modal no reconocido.'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
def send_message_api(request):
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
                conversation=conversation, sender=current_user, content=encrypted_content, msg_type='text'
            )
            conversation.save()

            return JsonResponse({
                'status': 'success', 
                'message': 'Mensaje cifrado guardado correctamente.',
                'message_id': nuevo_mensaje.id,
                'timestamp': nuevo_mensaje.timestamp.strftime('%H:%M')
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)


@csrf_exempt
def delete_message_api(request, message_id):
    if request.method == 'POST':
        try:
            mensaje = get_object_or_404(Message, id=message_id)
            current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]
            
            if mensaje.sender != current_user and current_user.username != "invitado":
                return JsonResponse({'status': 'error', 'message': 'No tienes permisos.'}, status=403)
            
            mensaje.delete()
            return JsonResponse({'status': 'success', 'message': 'Mensaje eliminado del servidor.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)
@csrf_exempt
@require_POST
def save_contact_api(request):
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'status': 'error', 'message': 'Sesión expirada.'}, status=401)

        data = json.loads(request.body)
        contact_id = data.get('contact_id')
        name = data.get('name', '').strip()
        # Solo dígitos, para que coincida siempre con el username
        phone_number = ''.join(filter(str.isdigit, data.get('phone_number', '')))
        public_key = data.get('public_key', '').strip()

        if not name or not phone_number:
            return JsonResponse({'status': 'error', 'message': 'Campos obligatorios incompletos.'}, status=400)

        associated_user = User.objects.filter(username=phone_number).first()

        if contact_id:
            contact_obj = get_object_or_404(Contact, id=contact_id, user=request.user)
            contact_obj.name = name
            contact_obj.phone_number = phone_number
            contact_obj.contact = associated_user
            if public_key:
                contact_obj.public_key = public_key
            contact_obj.save()
            message = 'Contacto actualizado con éxito.'
        else:
            Contact.objects.create(
                user=request.user,
                contact=associated_user,
                name=name,
                phone_number=phone_number,
                public_key=public_key,
            )
            message = 'Contacto guardado correctamente.'

        return JsonResponse({'status': 'success', 'message': message})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_POST
def delete_contact_api(request, contact_id):
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'status': 'error', 'message': 'Sesión no válida.'}, status=401)

        contact = get_object_or_404(Contact, id=contact_id, user=request.user)
        contact.delete()
        return JsonResponse({'status': 'success', 'message': 'Contacto eliminado de la lista.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_POST
def update_security_level_api(request):
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'status': 'error', 'message': 'Sesión no válida.'}, status=401)

        data = json.loads(request.body)
        security_level = data.get('security_level')

        if security_level is None:
            return JsonResponse({'status': 'error', 'message': 'Nivel de seguridad requerido.'}, status=400)

        sec_int = int(security_level)
        if sec_int not in (0, 1):
            return JsonResponse({'status': 'error', 'message': 'Nivel inválido.'}, status=400)

        profile_obj, _ = UserProfile.objects.get_or_create(user=request.user)
        profile_obj.security_level = sec_int
        profile_obj.save()

        return JsonResponse({'status': 'success', 'message': 'Nivel de seguridad actualizado correctamente.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ==========================================
# 3. INTERFACES Y APIS DE GRUPOS (Sincronizados)
# ==========================================

def group_detail_view(request, group_id):
    """
    Provee los participantes en HTML o JSON para pre-tildar a los miembros actuales.
    """
    group = get_object_or_404(Conversation, id=group_id, is_group=True)
    members = group.participants.all()

    if request.GET.get('format') == 'json':
        member_phones = [m.username for m in members]
        return JsonResponse({
            'id': group.id,
            'name': group.name,
            'members': member_phones
        })

    current_user = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")
    members_context = []
    
    for m in members:
        contact_record = Contact.objects.filter(user=current_user, phone_number=m.username).first()
        members_context.append({
            'username': m.username,
            'contact_name': contact_record.name if contact_record else None,
            'is_current_user': (m.id == current_user.id)
        })

    return render(request, 'group.html', {
        'group': group,
        'members': members_context
    })

@csrf_exempt
@require_POST
def edit_group_api(request, group_id):
    """
    LÓGICA DE ALTA INTEGRIDAD COMPLETA: Modifica el nombre, sanitiza de forma estricta los miembros,
    y asegura la creación del registro en caliente si el contacto aún no existe en la plataforma (auth_user).
    """
    try:
        group = get_object_or_404(Conversation, id=group_id, is_group=True)
        data = json.loads(request.body)
        new_name = data.get('name', '').strip()
        selected_member_phones = data.get('members', [])

        if not new_name:
            return JsonResponse({'status': 'error', 'message': 'El nombre es requerido.'}, status=400)

        # 1. Actualización del nombre de la sala
        group.name = new_name
        group.save()

        # 2. Sanitizado estricto de números: extrae solo los dígitos numéricos entrantes
        clean_phones = [''.join(filter(str.isdigit, str(phone))) for phone in selected_member_phones if phone]

        # 3. Mapeo y creación segura en caliente por número de teléfono
        matching_users = []
        for phone in clean_phones:
            # 🛠️ CORRECCIÓN CLAVE: get_or_create asegura que si Marito no existe en la tabla de usuarios, 
            # Django lo cree de forma instantánea en la BD para que el ManyToMany no falle ni lo ignore.
            user_obj, created = User.objects.get_or_create(username=phone)
            if created:
                # Inicializamos su perfil criptográfico base asociado de forma segura
                UserProfile.objects.get_or_create(user=user_obj)
            
            matching_users.append(user_obj)

        # 4. Sincronización real ManyToMany: asienta y graba los cambios de tildes de forma persistente
        group.participants.set(matching_users)

        # 5. Aseguramos la permanencia del usuario operador actual dentro del grupo grupal
        if request.user.is_authenticated and request.user not in group.participants.all():
            group.participants.add(request.user)

        return JsonResponse({'status': 'success', 'message': 'Grupo actualizado con éxito.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt
@require_POST
def create_group_api(request):
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        member_phones = data.get('members', [])

        if not name:
            return JsonResponse({'status': 'error', 'message': 'El nombre del grupo es obligatorio.'}, status=400)

        # 1. Obtener usuario de la sesión o forzar el usuario "invitado" de forma segura sin fallar por autenticación
        if hasattr(request, 'user') and request.user.is_authenticated:
            current_user = request.user
        else:
            current_user, _ = User.objects.get_or_create(username="invitado")

        # 2. Crear la conversación/grupo
        new_group = Conversation.objects.create(name=name, is_group=True, created_by=current_user)
        
        # 3. Asignar participantes
        clean_phones = [''.join(filter(str.isdigit, str(phone))) for phone in member_phones if phone]
        users_to_add = User.objects.filter(username__in=clean_phones)
        
        new_group.participants.set(users_to_add)
        new_group.participants.add(current_user)

        return JsonResponse({'status': 'success', 'message': 'Grupo creado exitosamente.'})

    except Exception as e:
        # Imprimir en la consola de Vercel para depuración directa si ocurre otro problema
        print(f"Error en create_group_api: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)




@csrf_exempt
@require_POST
def delete_group_api(request, group_id):
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'status': 'error', 'message': 'Sesión no válida.'}, status=401)

        # Solo los miembros del grupo pueden operar sobre él
        group = get_object_or_404(
            Conversation,
            id=group_id,
            is_group=True,
            participants=request.user
        )

        if group.created_by == request.user:
            # El creador elimina el grupo para todos
            group.delete()
            message = 'Grupo eliminado correctamente.'
        else:
            # Un miembro común solo se sale del grupo
            group.participants.remove(request.user)
            message = 'Saliste del grupo.'

        return JsonResponse({'status': 'success', 'message': message})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def logout_view(request):
    logout(request)
    return redirect('onboard')




def _call_peer(llamada, user):
    if llamada.emisor_id == user.id:
        return llamada.receptor_principal
    if llamada.receptor_principal_id == user.id:
        return llamada.emisor
    return None


@csrf_exempt
@require_POST
def start_call_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Sesión expirada.'}, status=401)

    data = json.loads(request.body)
    phone = ''.join(filter(str.isdigit, str(data.get('phone', ''))))
    target = User.objects.filter(username=phone).first()

    if not target or target.id == request.user.id:
        return JsonResponse({'status': 'error', 'message': 'Destinatario inválido.'}, status=400)

    tipo = 'VI' if data.get('tipo') == 'VI' else 'VO'
    llamada = Llamada.objects.create(
        emisor=request.user,
        receptor_principal=target,
        tipo=tipo
    )

    return JsonResponse({'status': 'success', 'call_id': llamada.id})


def pending_call_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Sesión expirada.'}, status=401)

    limite = timezone.now() - timedelta(seconds=45)

    llamada = Llamada.objects.filter(
        receptor_principal=request.user,
        estado='PE',
        fecha_inicio__gte=limite
    ).order_by('-fecha_inicio').first()

    if not llamada:
        return JsonResponse({'status': 'success', 'call': None})

    contacto = Contact.objects.filter(
        user=request.user,
        phone_number=llamada.emisor.username
    ).first()

    return JsonResponse({
        'status': 'success',
        'call': {
            'id': llamada.id,
            'from': llamada.emisor.username,
            'name': contacto.name if contacto else llamada.emisor.username,
            'tipo': llamada.tipo,
        }
    })


@csrf_exempt
@require_POST
def call_signal_api(request, call_id):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Sesión expirada.'}, status=401)

    llamada = get_object_or_404(Llamada, id=call_id)
    peer = _call_peer(llamada, request.user)

    if not peer:
        return JsonResponse({'status': 'error', 'message': 'No autorizado.'}, status=403)

    data = json.loads(request.body)
    kind = data.get('kind')

    if kind not in ('offer', 'answer', 'ice'):
        return JsonResponse({'status': 'error', 'message': 'Tipo inválido.'}, status=400)

    CallSignal.objects.create(
        llamada=llamada,
        sender=request.user,
        receiver=peer,
        kind=kind,
        payload=json.dumps(data.get('payload'))
    )

    return JsonResponse({'status': 'success'})


def call_signals_api(request, call_id):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Sesión expirada.'}, status=401)

    llamada = get_object_or_404(Llamada, id=call_id)

    if not _call_peer(llamada, request.user):
        return JsonResponse({'status': 'error', 'message': 'No autorizado.'}, status=403)

    after = int(request.GET.get('after', 0) or 0)

    signals = CallSignal.objects.filter(
        llamada=llamada,
        receiver=request.user,
        id__gt=after
    ).order_by('id')

    return JsonResponse({
        'status': 'success',
        'estado': llamada.estado,
        'signals': [
            {
                'id': s.id,
                'kind': s.kind,
                'payload': json.loads(s.payload)
            }
            for s in signals
        ]
    })


def call_room(request, room_id):
    if not request.user.is_authenticated:
        return redirect('onboard')

    llamada = get_object_or_404(Llamada, id=room_id)

    if llamada.emisor_id != request.user.id and llamada.receptor_principal_id != request.user.id:
        return redirect('home')

    is_caller = llamada.emisor_id == request.user.id
    peer = _call_peer(llamada, request.user)
    peer_name = peer.username if peer else 'Contacto'

    if peer:
        contacto = Contact.objects.filter(
            user=request.user,
            phone_number=peer.username
        ).first()

        if contacto and contacto.name:
            peer_name = contacto.name

    return render(request, 'call_room.html', {
        'room_id': room_id,
        'llamada': llamada,
        'is_caller': is_caller,
        'peer_name': peer_name,
    })


def call_history(request):
    if not request.user.is_authenticated:
        return redirect("onboard")

    calls = Llamada.objects.filter(
        Q(emisor=request.user) | Q(receptor_principal=request.user)
    ).select_related(
        "emisor", "receptor_principal"
    ).order_by("-fecha_inicio")

    for llamada in calls:
        contacto_user = (
            llamada.receptor_principal
            if llamada.emisor == request.user
            else llamada.emisor
        )

        llamada.contact_phone = contacto_user.username if contacto_user else ""
        llamada.contact_name = contacto_user.username if contacto_user else "Usuario"

        if contacto_user:
            contacto = Contact.objects.filter(
                user=request.user,
                phone_number=contacto_user.username
            ).first()

            if contacto and contacto.name:
                llamada.contact_name = contacto.name

    return render(request, "call_history.html", {"calls": calls})


@require_POST
def delete_call_history(request, call_id):
    if not request.user.is_authenticated:
        return redirect("onboard")

    llamada = get_object_or_404(Llamada, id=call_id)

    if llamada.emisor == request.user or llamada.receptor_principal == request.user:
        llamada.delete()
        messages.success(request, "Llamada eliminada correctamente")

    return redirect("call_history")


@csrf_exempt
@require_POST
def call_state_api(request, call_id):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Sesión expirada.'}, status=401)

    llamada = get_object_or_404(Llamada, id=call_id)

    if not _call_peer(llamada, request.user):
        return JsonResponse({'status': 'error', 'message': 'No autorizado.'}, status=403)

    estado = json.loads(request.body).get('estado')

    if estado not in ('CO', 'RE', 'FI'):
        return JsonResponse({'status': 'error', 'message': 'Estado inválido.'}, status=400)

    llamada.estado = estado
    llamada.save()

    return JsonResponse({'status': 'success'})