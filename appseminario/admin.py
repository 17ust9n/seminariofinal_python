from django.contrib import admin
from .models import UserProfile, Contact, Conversation, Message, Llamada


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'security_level', 'pub_key')
    search_fields = ('user__username', 'pub_key')
    list_filter = ('security_level',)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone_number', 'user', 'contact', 'visible_in_home')
    search_fields = ('name', 'phone_number', 'user__username')
    list_filter = ('visible_in_home',)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_group', 'created_by', 'updated_at')
    list_filter = ('is_group',)
    filter_horizontal = ('participants',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'conversation', 'msg_type', 'timestamp')
    list_filter = ('msg_type', 'timestamp')
    search_fields = ('content', 'sender__username')


@admin.register(Llamada)
class LlamadaAdmin(admin.ModelAdmin):
    list_display = ('id', 'emisor', 'receptor_principal', 'estado', 'fecha_inicio', 'duracion_segundos')
    list_filter = ('estado', 'fecha_inicio')
    search_fields = ('emisor__username', 'receptor_principal__username')