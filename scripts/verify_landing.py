import os
import django
from django.template.loader import render_to_string
from django.test import RequestFactory

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ims.settings')
django.setup()

factory = RequestFactory()
request = factory.get('/')

# Mock context
context = {
    'starter_plans': [],
}

rendered = render_to_string('pages/landing_page.html', context, request)

if 'id="termsModal"' in rendered and 'id="privacyModal"' in rendered:
    print("SUCCESS: Modals found in rendered template")
else:
    print("ERROR: Modals NOT found in rendered template")
    
if 'data-bs-target="#termsModal"' in rendered and 'data-bs-target="#privacyModal"' in rendered:
    print("SUCCESS: Links found in rendered template")
else:
    print("ERROR: Links NOT found in rendered template")
