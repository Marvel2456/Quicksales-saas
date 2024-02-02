from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.loginUser, name='login'),
    path('logout/', views.logoutUser, name='logout'),
    path('pos/', views.terminal, name='pos'),
    path('editpos/', views.editPos, name='editpos'),
    path('deletepos/', views.deletePos, name='deletepos'),
    path('branch/', views.createBranch, name='branch'),
    path('editbranch/', views.editBranch, name='editbranch'),
    path('deletebranch/', views.deleteBranch, name='deletebranch'),
    path('posview/<str:pk>/', views.posView, name='posview'),
    path('branchview/<str:pk>/', views.branchView, name='branchview'),
    path('posstaff/<str:pk>/', views.staffPosView, name='posstaff'),
    path('possale/<str:pk>/', views.posSaleView, name='possale'),
]