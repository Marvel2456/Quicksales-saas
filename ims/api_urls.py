from django.urls import path
from ims import api_views

urlpatterns = [
    path('status/', api_views.api_inventory_status, name='api_inventory_status'),
    path('products/', api_views.api_product_list, name='api_product_list'),
    path('query/', api_views.api_product_detail, name='api_product_detail'),
]
