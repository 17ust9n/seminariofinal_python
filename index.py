import os
import sys
from django.core.wsgi import get_wsgi_application

# Agrega la raíz al PATH para que Django encuentre las aplicaciones internas
sys.path.append(os.path.dirname(__file__))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'infoseminario.settings')

# Vercel Serverless Python busca la variable 'app'
app = get_wsgi_application()