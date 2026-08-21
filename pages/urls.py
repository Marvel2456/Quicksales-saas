from django.urls import path
from . import views


urlpatterns = [
    path('', views.landingPage, name='landing_page'),
    path('docs/', views.api_docs, name='api_docs'),
    path('download/windows/', views.download_windows, name='download_windows'),
    path('download/mac/', views.download_mac, name='download_mac'),
]
