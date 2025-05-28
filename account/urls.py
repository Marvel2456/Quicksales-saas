from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.loginUser, name='login'),
    path('logout/', views.logoutUser, name='logout'),
    path('branch/', views.createBranch, name='branch'),
    path('editbranch/', views.editBranch, name='editbranch'),
    path('deletebranch/', views.deleteBranch, name='deletebranch'),
    path('branchview/<str:pk>/', views.branchView, name='branchview'),
]