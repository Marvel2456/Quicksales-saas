from django.conf import settings


def paystack_public_key(request):
    return {"PAYSTACK_PUBLIC_KEY": settings.PAYSTACK_PUBLIC_KEY}
