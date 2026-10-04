import os
import sys
from django.core.wsgi import get_wsgi_application

# Sube un nivel desde /api para incluir la raíz del proyecto en el PATH
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'infoseminario.settings')

# Vercel Serverless Python ejecuta la variable 'app'
app = get_wsgi_application()