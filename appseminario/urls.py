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

    # --- API de Mensajes y Audios ---
    path('api/send-message/', views.send_message_api, name='send_message_api'),
    path('api/delete-message/<int:message_id>/', views.delete_message_api, name='delete_message_api'),
    path('api/hide-chat/<int:room_id>/', views.hide_chat_from_home_api, name='hide_chat_from_home_api'),
    path('api/search-users/', views.search_users_api, name='search_users_api'),
    path('api/update-security-level/', views.update_security_level_api, name='update_security_level_api'),

    path('logout/', views.logout_view, name='logout'),
]