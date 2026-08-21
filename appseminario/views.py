import json
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

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
    Muestra la sala de chat e inyecta el nombre guardado del contacto para 'chName'.
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

    # Identificar al otro participante para extraer su nombre de la agenda de contactos
    other_participant = conversation.participants.exclude(id=current_user.id).first()
    display_name = "Chat"

    if conversation.is_group:
        display_name = conversation.name or "Grupo sin nombre"
    elif other_participant:
        contact = Contact.objects.filter(user=current_user, phone_number=other_participant.username).first()
        display_name = contact.name if (contact and contact.name) else other_participant.username

    messages = conversation.messages.order_by('timestamp')

    return render(request, 'chat.html', {
        'conversation': conversation,
        'messages': messages,
        'display_name': display_name
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


def onboard(request):
    if request.method == 'POST':
        phone = request.POST.get('phone')
        if phone:
            user, _ = User.objects.get_or_create(username=phone)
            login(request, user)
            return JsonResponse({'status': 'success', 'redirect_url': '/home/'})
        return JsonResponse({'status': 'error', 'message': 'Teléfono requerido'}, status=400)

    return render(request, 'onboard.html')


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
            else:
                Contact.objects.create(
                    user=current_user, 
                    name=name, 
                    phone_number=phone, 
                    contact=target_user,
                    visible_in_home=True
                )

            return JsonResponse({'status': 'success'})

        # B) Eliminar Contacto
        elif modal_type == 'deleteContact':
            contact_id = data.get('cId')
            contact = Contact.objects.filter(id=contact_id, user=current_user).first()
            
            if contact:
                # 1. Buscar al usuario asociado por su número de teléfono
                target_user = User.objects.filter(username=contact.phone_number).first()
                
                # 2. Eliminar la conversación activa en Home si existe
                if target_user:
                    conversations = Conversation.objects.filter(
                        is_group=False, 
                        participants=current_user
                    ).filter(participants=target_user)
                    conversations.delete()

                # 3. Eliminar el contacto de la agenda
                contact.delete()

                return JsonResponse({'status': 'success'})
            else:
                return JsonResponse({'status': 'error', 'message': 'El contacto no existe.'}, status=404)

        return JsonResponse({'status': 'error', 'message': f'Acción no válida: {modal_type}'}, status=400)

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ==========================================
# 3. API DE MENSAJES
# ==========================================

@csrf_exempt
def send_message_api(request):
    if request.method == 'POST':
        conversation_id = request.POST.get('conversation_id')
        msg_type = request.POST.get('msg_type', 'text')
        
        if not conversation_id:
            return JsonResponse({'status': 'error', 'message': 'ID de conversación requerido'}, status=400)

        conversation = get_object_or_404(Conversation, id=conversation_id)
        sender = request.user if request.user.is_authenticated else User.objects.get_or_create(username="invitado")[0]

        message = Message(conversation=conversation, sender=sender, msg_type=msg_type)

        if msg_type == 'audio' and 'audio_file' in request.FILES:
            message.audio_file = request.FILES['audio_file']
        else:
            message.content = request.POST.get('content', '')

        message.save()
        conversation.save()

        return JsonResponse({
            'status': 'success',
            'message_id': message.id,
            'audio_url': message.audio_file.url if message.audio_file else '',
            'content': message.content,
            'sender': message.sender.username,
            'msg_type': message.msg_type
        })

    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)


@csrf_exempt
def delete_message_api(request, message_id):
    if request.method == 'POST':
        message = get_object_or_404(Message, id=message_id)
        if message.msg_type == 'audio' and message.audio_file:
            message.audio_file.delete(save=False)
            
        message.delete()
        return JsonResponse({'status': 'success', 'message': 'Mensaje eliminado'})

    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)