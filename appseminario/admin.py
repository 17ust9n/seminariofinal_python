from django.contrib import admin
from .models import UserProfile, Contact, Conversation, Message, Llamada


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'status_text', 'is_online')
    search_fields = ('user__username', 'status_text')
    list_filter = ('is_online',)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone_number', 'user', 'contact', 'created_at')
    search_fields = ('name', 'phone_number', 'user__username')


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_group', 'created_by', 'created_at')
    list_filter = ('is_group',)
    filter_horizontal = ('participants',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'conversation', 'msg_type', 'timestamp', 'is_read')
    list_filter = ('msg_type', 'is_read', 'timestamp')
    search_fields = ('content', 'sender__username')


@admin.register(Llamada)
class LlamadaAdmin(admin.ModelAdmin):
    list_display = ('id', 'emisor', 'tipo', 'estado', 'fecha_inicio', 'duracion_segundos')
    list_filter = ('tipo', 'estado', 'fecha_inicio')
    filter_horizontal = ('invitados',)