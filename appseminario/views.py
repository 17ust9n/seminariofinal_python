from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST
import json

from .models import UserProfile, Conversation, Message, Contact, Llamada


# ==========================================
# 1. PANTALLAS PRINCIPALES (HTML Render)
# ==========================================

@login_required
def home(request):
    """
    Pantalla principal (#home screen). Carga la lista de conversaciones
    y la agenda de contactos para la búsqueda (#homeSearch) y nuevo chat (#fab).
    """
    conversations = request.user.conversations.all()
    contacts = Contact.objects.filter(user=request.user)
    
    context = {
        'conversations': conversations,
        'contacts': contacts,
        'profile': request.user.profile,
    }
    return render(request, 'home.html', context)


@login_required
def chat(request):
    """Redirige al chat de la primera conversación activa o al home si no hay ninguna."""
    last_conv = request.user.conversations.first()
    if last_conv:
        return redirect('chat_detail', room_id=last_conv.id)
    return redirect('home')


@login_required
def chat_detail(request, room_id):
    """
    Pantalla de chat activo (#chatScreen). Carga la conversación y sus mensajes.
    Soporta conversaciones individuales y de grupo.
    """
    conversation = get_object_or_404(Conversation, id=room_id, participants=request.user)
    messages = conversation.messages.all()

    # Identificar la contraparte (para el avatar #chAv y subtítulo #chSub si es chat individual)
    other_participant = None
    if not conversation.is_group:
        other_participant = conversation.participants.exclude(id=request.user.id).first()

    context = {
        'conversation': conversation,
        'messages': messages,
        'other_participant': other_participant,
    }
    return render(request, 'chat.html', context)


@login_required
def call(request):
    """Redirige o muestra la pantalla general de llamadas."""
    recent_calls = Llamada.objects.filter(
        emisor=request.user
    ) | Llamada.objects.filter(receptor_principal=request.user)
    return render(request, 'call.html', {'calls': recent_calls.order_by('-fecha_inicio')})


@login_required
def call_room(request, room_id):
    """Soporte de interfaz de llamada o videollamada activa."""
    call_obj = get_object_or_404(Llamada, id=room_id)
    return render(request, 'call_room.html', {'call': call_obj})


@login_required
def newchat(request):
    """Vista de soporte previa a la apertura de un nuevo chat."""
    contacts = Contact.objects.filter(user=request.user)
    return render(request, 'newchat.html', {'contacts': contacts})


@login_required
def profile(request):
    """Pantalla de perfil del usuario logueado (avatar, estado #chSub, etc.)."""
    return render(request, 'profile.html', {'profile': request.user.profile})


def onboard(request):
    """Pantalla de onboarding/autenticación local."""
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, 'onboard.html')


# ==========================================
# 2. MODALES / ACCIONES ASÍNCRONAS (JSON API)
# ==========================================

@login_required
@require_POST
def modal_handler(request, modal_type):
    """
    Procesa las peticiones AJAX/Fetch generadas desde modal.html:
    - modal_type == 'mContact': guarda contacto (#cName, #cNum) -> saveContact()
    - modal_type == 'mGroup': crea nuevo grupo (#gName, #gPick) -> saveGroup()
    - modal_type == 'mInvite': invita usuarios a la llamada (#iPick) -> doInvite()
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST

    # 1. MODAL: Guardar nuevo contacto (#mContact)
    if modal_type == 'mContact':
        name = data.get('cName')
        phone = data.get('cNum')

        if not name or not phone:
            return JsonResponse({'status': 'error', 'message': 'Todos los campos son obligatorios'}, status=400)

        # Buscar si el teléfono coincide con un usuario registrado
        contact_user = UserProfile.objects.filter(user__username=phone).first()
        
        contact_obj, created = Contact.objects.get_or_create(
            user=request.user,
            phone_number=phone,
            defaults={
                'name': name,
                'contact': contact_user.user if contact_user else None
            }
        )
        if not created:
            contact_obj.name = name
            contact_obj.save()

        return JsonResponse({'status': 'success', 'message': 'Contacto guardado correctamente', 'contact_id': contact_obj.id})

    # 2. MODAL: Crear nuevo grupo (#mGroup)
    elif modal_type == 'mGroup':
        group_name = data.get('gName')
        member_ids = data.get('gPick', [])  # Lista de IDs de usuarios elegidos

        if not group_name:
            return JsonResponse({'status': 'error', 'message': 'Ingresá un nombre para el grupo'}, status=400)

        # Crear sala de conversación grupal
        conversation = Conversation.objects.create(
            name=group_name,
            is_group=True,
            created_by=request.user
        )
        conversation.participants.add(request.user)

        # Vincular participantes desde el picklist (#gPick)
        if member_ids:
            users = User.objects.filter(id__in=member_ids)
            conversation.participants.add(*users)

        return JsonResponse({'status': 'success', 'conversation_id': conversation.id})

    # 3. MODAL: Invitar participantes a la llamada (#mInvite)
    elif modal_type == 'mInvite':
        call_id = data.get('call_id')
        invited_ids = data.get('iPick', [])

        if not call_id:
            return JsonResponse({'status': 'error', 'message': 'ID de llamada no especificado'}, status=400)

        call_obj = get_object_or_404(Llamada, id=call_id)
        
        if invited_ids:
            users_to_invite = User.objects.filter(id__in=invited_ids)
            call_obj.invitados.add(*users_to_invite)

        return JsonResponse({'status': 'success', 'message': 'Invitaciones enviadas correctamente'})

    return JsonResponse({'status': 'error', 'message': 'Tipo de modal no reconocido'}, status=400)