from django.urls import path
from . import views, vendor_views

urlpatterns = [
    # Buyer Portal & Universal Auth
    path('buyer/register/', views.buyer_register_view, name='buyer_register'),
    path('buyer/login/', views.buyer_login_view, name='buyer_login'),
    path('buyer/logout/', views.buyer_logout_view, name='buyer_logout'),
    path('buyer/dashboard/', views.buyer_dashboard_view, name='buyer_dashboard'),

    # Vendor Store Management (Dashboard)
    path('dashboard/store/settings/', vendor_views.store_settings, name='store_settings'),
    path('dashboard/store/listings/', vendor_views.manage_listings, name='manage_listings'),
    path('dashboard/store/orders/', vendor_views.vendor_order_list, name='vendor_order_list'),
    path('dashboard/store/orders/<uuid:order_id>/', vendor_views.vendor_order_detail, name='vendor_order_detail'),
    path('dashboard/store/discounts/', vendor_views.vendor_discounts, name='vendor_discounts'),
    path('dashboard/store/payouts/', vendor_views.vendor_payouts, name='vendor_payouts'),
    path('dashboard/store/bank/verify/', vendor_views.verify_bank_account_api, name='vendor_verify_bank_account'),
    path('dashboard/store/customers/', vendor_views.vendor_customers, name='vendor_customers'),

    # Public Storefront & Shopping Cart
    path('store/<slug:org_slug>/', views.storefront, name='storefront'),
    path('store/<slug:org_slug>/product/<uuid:listing_id>/', views.product_detail, name='product_detail'),
    path('store/<slug:org_slug>/cart/add/', views.add_to_cart_api, name='store_add_to_cart'),
    path('store/<slug:org_slug>/cart/update/', views.update_cart_api, name='store_update_cart'),
    path('store/<slug:org_slug>/checkout/', views.store_checkout, name='store_checkout'),
    path('store/<slug:org_slug>/payment/callback/', views.store_payment_callback, name='store_payment_callback'),
    path('store/<slug:org_slug>/order/<str:order_number>/', views.order_success, name='order_success'),
]
