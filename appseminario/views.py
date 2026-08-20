from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST
import json

from .models import UserProfile, Conversation, Message, Contact, Llamada


# ==========================================
# 1. PANTALLAS PRINCIPALES (HTML Render)
# ==========================================

def home(request):
    """
    Pantalla principal (#home screen). Carga la lista de conversaciones.
    JS maneja la validación de inicio mediante LocalStorage.
    """
    conversations = request.user.conversations.all() if request.user.is_authenticated else []
    contacts = Contact.objects.filter(user=request.user) if request.user.is_authenticated else []
    profile = getattr(request.user, 'profile', None) if request.user.is_authenticated else None
    
    context = {
        'conversations': conversations,
        'contacts': contacts,
        'profile': profile,
    }
    return render(request, 'home.html', context)


def chat(request):
    """
    Lee ?to=PHONE desde la URL, asegura que existan los usuarios
    y la conversación, y redirige a la sala correspondiente.
    """
    phone = request.GET.get('to')

    if phone:
        # 1. Asegurar que exista un usuario de Django asociado a ese teléfono
        target_user, _ = User.objects.get_or_create(username=phone)
        UserProfile.objects.get_or_create(user=target_user)

        # 2. Si el usuario actual no está autenticado, asignarle una sesión básica o invocar su usuario
        current_user = request.user
        if not current_user.is_authenticated:
            current_user, _ = User.objects.get_or_create(username="invitado")

        # 3. Recuperar o crear la conversación privada entre ambos
        conversation = Conversation.objects.filter(
            is_group=False,
            participants=current_user
        ).filter(participants=target_user).first()

        if not conversation:
            conversation = Conversation.objects.create(
                is_group=False,
                created_by=current_user
            )
            conversation.participants.add(current_user, target_user)

        # Redirigir directamente al detalle del chat mediante su ID
        return redirect('chat_detail', room_id=conversation.id)

    return redirect('home')


def chat_detail(request, room_id):
    """Carga la plantilla chat.html con la conversación activa."""
    conversation = get_object_or_404(Conversation, id=room_id)
    messages = conversation.messages.all()

    other_participant = conversation.participants.exclude(id=request.user.id).first()

    context = {
        'conversation': conversation,
        'messages': messages,
        'other_participant': other_participant,
        'target_phone': getattr(other_participant, 'username', ''),
    }
    return render(request, 'chat.html', context)


def call(request):
    """Muestra la pantalla general de llamadas."""
    recent_calls = []
    if request.user.is_authenticated:
        recent_calls = (Llamada.objects.filter(emisor=request.user) | 
                        Llamada.objects.filter(receptor_principal=request.user)).order_by('-fecha_inicio')
    return render(request, 'call.html', {'calls': recent_calls})


def call_room(request, room_id):
    """Interfaz de llamada activa."""
    call_obj = get_object_or_404(Llamada, id=room_id)
    return render(request, 'call_room.html', {'call': call_obj})


def newchat(request):
    """Vista de soporte previa a la apertura de un nuevo chat."""
    contacts = Contact.objects.filter(user=request.user) if request.user.is_authenticated else []
    return render(request, 'newchat.html', {'contacts': contacts})


def profile(request):
    """Pantalla de perfil."""
    prof = getattr(request.user, 'profile', None) if request.user.is_authenticated else None
    return render(request, 'profile.html', {'profile': prof})


def onboard(request):
    """Pantalla de onboarding/autenticación local."""
    if request.method == 'POST':
        phone = request.POST.get('phone')
        if phone:
            user, _ = User.objects.get_or_create(username=phone)
            login(request, user)  # Inicia sesión también en el backend si envías la petición por POST
            return JsonResponse({'status': 'success', 'redirect_url': '/home/'})
        return JsonResponse({'status': 'error', 'message': 'Teléfono requerido'}, status=400)

    # Renderiza directamente la plantilla de onboarding sin redireccionar en Python
    return render(request, 'onboard.html')


# ==========================================
# 2. MODALES / ACCIONES ASÍNCRONAS (JSON API)
# ==========================================

@require_POST
def modal_handler(request, modal_type):
    """Procesa las peticiones AJAX/Fetch generadas desde los modales."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST

    # 1. MODAL: Guardar nuevo contacto
    if modal_type == 'mContact':
        name = data.get('cName')
        phone = data.get('cNum')

        if not name or not phone:
            return JsonResponse({'status': 'error', 'message': 'Todos los campos son obligatorios'}, status=400)

        if not request.user.is_authenticated:
            return JsonResponse({'status': 'error', 'message': 'Usuario no autenticado en servidor'}, status=401)

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

    # 2. MODAL: Crear nuevo grupo
    elif modal_type == 'mGroup':
        group_name = data.get('gName')
        member_ids = data.get('gPick', [])

        if not group_name:
            return JsonResponse({'status': 'error', 'message': 'Ingresá un nombre para el grupo'}, status=400)

        if not request.user.is_authenticated:
            return JsonResponse({'status': 'error', 'message': 'Usuario no autenticado en servidor'}, status=401)

        conversation = Conversation.objects.create(
            name=group_name,
            is_group=True,
            created_by=request.user
        )
        conversation.participants.add(request.user)

        if member_ids:
            users = User.objects.filter(id__in=member_ids)
            conversation.participants.add(*users)

        return JsonResponse({'status': 'success', 'conversation_id': conversation.id})

    # 3. MODAL: Invitar a llamada
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