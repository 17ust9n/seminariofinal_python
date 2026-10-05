import os
from django.core.wsgi import get_wsgi_application
from django.core.management import call_command

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'infoseminario.settings')

app = get_wsgi_application()

# Forzar migraciones automáticas en la BD /tmp/db.sqlite3 si no existen las tablas
try:
    call_command('migrate', interactive=False)
except Exception as e:
    print(f"Error ejecutando migraciones: {e}")