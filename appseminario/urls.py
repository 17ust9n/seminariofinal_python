from django.urls import path
from . import views

urlpatterns = [
    # --- Pantalla Inicial (Onboarding) ---
    path('', views.onboard, name='onboard'),
    
    # --- Pantallas Principales ---
    path('home/', views.home, name='home'),
    path('chat/', views.chat, name='chat'),
    path('chat/<str:room_id>/', views.chat_detail, name='chat_detail'),
    path('call/', views.call, name='call'),
    path('call/<str:room_id>/', views.call_room, name='call_room'),
    path('newchat/', views.newchat, name='newchat'),
    path('profile/', views.profile, name='profile'),
    path('edit_profile/', views.edit_profile, name='edit_profile'),
    path('settings/', views.settings, name='settings'),
    path('about/', views.about, name='about'),
    path('terms/', views.terms, name='terms'),

    # --- Modales / Acciones Asíncronas ---
    path('modal/<str:modal_type>/', views.modal_handler, name='modal_handler'),

    # --- API de Mensajes y Contactos ---
    path('api/send-message/', views.send_message_api, name='send_message_api'),
    path('api/delete-message/<int:message_id>/', views.delete_message_api, name='delete_message_api'),
    path('api/hide-chat/<int:room_id>/', views.hide_chat_from_home_api, name='hide_chat_from_home_api'),
    path('api/search-users/', views.search_users_api, name='search_users_api'),
    path('api/delete-contact/<int:contact_id>/', views.delete_contact_api, name='delete_contact_api'),
    path('api/update-security-level/', views.update_security_level_api, name='update_security_level_api'),
    
    

    # --- API de Grupos ---
    path('api/create-group/', views.create_group_api, name='create_group_api'),
    path('api/edit-group/<int:group_id>/', views.edit_group_api, name='edit_group_api'),
    path('api/delete-group/<int:group_id>/', views.delete_group_api, name='delete_group_api'),
    
    # 🔑 AGREGA ESTA LÍNEA CRÍTICA PARA SOLUCIONAR EL ERROR 404:
    path('actualizar-clave-publica/', views.actualizar_clave_publica_api, name='actualizar_clave_publica_api'),



    path('logout/', views.logout_view, name='logout'),
]