import os
import sys

# Agrega la raíz del proyecto al PATH para encontrar infoseminario
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'infoseminario.settings')

from django.core.wsgi import get_wsgi_application

app = get_wsgi_application()