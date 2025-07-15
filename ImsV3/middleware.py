from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin
from account.models import Organization

# class SubdomainOrganizationMiddleware(MiddlewareMixin):
#     def process_request(self, request):
#         host = request.get_host().split(':')[0]  # remove port
#         parts = host.split('.')

#         if len(parts) < 3:
#             request.organization = None  # Root domain (e.g. landing page)
#             return

#         subdomain = parts[0]

#         try:
#             request.organization = Organization.objects.get(slug=subdomain)
#         except Organization.DoesNotExist:
#             return HttpResponse("Organization not found", status=404)


class SubdomainOrganizationMiddleware(MiddlewareMixin):
    def process_request(self, request):
        host = request.get_host().split(':')[0]
        parts = host.split('.')

        # Root domain (e.g., landing page or docs.yourapp.com)
        if len(parts) < 3:
            request.organization = None
            return

        subdomain = parts[0]

        try:
            request.organization = Organization.objects.get(slug=subdomain)
        except Organization.DoesNotExist:
            return HttpResponse("Organization not found", status=404)

        # Authorization check: ensure logged-in user's org matches the subdomain
        if request.user.is_authenticated:
            user_org = getattr(request.user, "organization", None)
            if user_org and user_org != request.organization:
                return HttpResponse("Organization mismatch", status=403)