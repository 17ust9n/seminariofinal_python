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

    # --- Modales / Acciones Asíncronas ---
    path('modal/<str:modal_type>/', views.modal_handler, name='modal_handler'),
]