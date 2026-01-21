from django.urls import path
from . import views
from . import coupon_views

urlpatterns = [
    path('settings/', views.settingsView, name='settings'),
    path('settings/edit_organization/<uuid:pk>/', views.editOrganization, name='edit_organization'),
    path("plan/init/<uuid:plan_id>/", views.init_payment, name="init_payment"),
    path("plan/create_payment/", views.create_payment, name="create_payment"),
    path("plan/verify/", views.verify_payment, name="verify_payment"),
    path("plan/cancel/<uuid:subscription_id>/", views.cancel_plan, name="cancel_plan"),

    # Paystack webhook (asynchronous notification from Paystack)
    path("webhook/paystack/", views.paystack_webhook, name="paystack_webhook"),
    
    # Coupon endpoints
    path("api/validate-coupon/", coupon_views.validate_coupon_api, name="validate_coupon_api"),
    path("api/apply-coupon/<uuid:subscription_id>/", coupon_views.apply_coupon_to_subscription, name="apply_coupon_to_subscription"),
]
