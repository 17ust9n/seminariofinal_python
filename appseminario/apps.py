from django.apps import AppConfig

class AppseminarioConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'appseminario'

    def ready(self):
        # Activación de los Observers (Señales) al iniciar el servidor
        import appseminario.signals 
