from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin
from account.models import Organization

class SubdomainOrganizationMiddleware(MiddlewareMixin):
    def process_request(self, request):
        host = request.get_host().split(':')[0]  # remove port
        parts = host.split('.')

        if len(parts) < 3:
            request.organization = None  # Root domain (e.g. landing page)
            return

        subdomain = parts[0]

        try:
            request.organization = Organization.objects.get(slug=subdomain)
        except Organization.DoesNotExist:
            return HttpResponse("Organization not found", status=404)
