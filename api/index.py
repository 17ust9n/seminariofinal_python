import os
import sys

# Agregar la raíz del proyecto al PATH para encontrar infoseminario
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'infoseminario.settings')

from django.core.wsgi import get_wsgi_application

# Vercel Serverless busca la variable 'app'
app = get_wsgi_application()