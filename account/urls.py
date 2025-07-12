from django.urls import path
from . import views
from .views import OwnerRegisterView

urlpatterns = [
    path('login/', views.loginUser, name='login'),
    path('logout/', views.logoutUser, name='logout'),
    path('branch/', views.createBranch, name='branch'),
    path('editbranch/', views.editBranch, name='editbranch'),
    path('deletebranch/', views.deleteBranch, name='deletebranch'),
    path('branchview/<str:pk>/', views.branchView, name='branchview'),
    path('register/', OwnerRegisterView.as_view(), name='register'),
    path('verify-email/<uidb64>/<token>/', views.verifyEmail, name='verify_email')

]