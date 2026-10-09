from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse
from .models import Buyer


def get_logged_in_buyer(request):
    """
    Returns the currently logged in Buyer instance from session, or None.
    """
    buyer_id = request.session.get('buyer_id')
    if buyer_id:
        try:
            return Buyer.objects.get(id=buyer_id, is_active=True)
        except (Buyer.DoesNotExist, ValueError):
            request.session.pop('buyer_id', None)
    return None


def buyer_login(request, buyer):
    """
    Log in a buyer by storing their UUID in the Django session.
    """
    request.session['buyer_id'] = str(buyer.id)
    request.session['buyer_email'] = buyer.email
    request.session['buyer_name'] = buyer.get_full_name()


def buyer_logout(request):
    """
    Log out a buyer.
    """
    request.session.pop('buyer_id', None)
    request.session.pop('buyer_email', None)
    request.session.pop('buyer_name', None)


def buyer_required(view_func):
    """
    Decorator for buyer-only views (like order history).
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        buyer = get_logged_in_buyer(request)
        if not buyer:
            next_url = request.get_full_path()
            return redirect(f"{reverse('buyer_login')}?next={next_url}")
        request.buyer = buyer
        return view_func(request, *args, **kwargs)
    return _wrapped
