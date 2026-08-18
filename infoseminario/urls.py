from django.contrib import admin
from django.urls import path, include
from django.conf import settings                 # Para leer la configuración de settings.py
from django.conf.urls.static import static       # Para habilitar la ruta de archivos en desarrollo

urlpatterns = [
    # Panel de administración por defecto de Django
    path('admin/', admin.site.urls),
    
    # Conecta de forma global con todas las rutas que tenés escritas en tu appseminario
    path('', include('appseminario.urls')),          
]

# Vincula la carpeta /media/ externa al sistema de rutas solo durante el desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
