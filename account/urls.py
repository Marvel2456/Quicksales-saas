from django.urls import path
from . import views
from .views import OwnerRegisterView

urlpatterns = [
    path('login/', views.loginUser, name='login'),
    path('logout/', views.logoutUser, name='logout'),
    path('branch/', views.createBranch, name='branch'),
    path('editbranch/', views.editBranch, name='editbranch'),
    path('deletebranch/', views.deleteBranch, name='deletebranch'),
    # path('branchview/<str:pk>/', views.branchView, name='branchview'),
    # path('editbranch/<uuid:pk>/', views.edit_branch, name='edit_branch'),
    path('register/', OwnerRegisterView.as_view(), name='register'),
    path('verify-email/<uidb64>/<token>/', views.verifyEmail, name='verify_email'),
    path('account/', views.accountView, name='account'),
    path('account/update-profile/', views.update_profile, name='update_profile'),
    path('account/change-password/', views.change_password, name='change_password'),
    path('account/force-password-change/', views.force_password_change, name='force_password_change'),
    path('settings/update-branding/', views.update_organization_branding, name='update_organization_branding'),
    # Notifications
    path('notifications/', views.notifications_view, name='notifications'),
    path('notifications/<uuid:pk>/delete/', views.delete_notification, name='notification_delete'),
    # path('settings/', views.settingsView, name='settings'),
    # path("settings/edit_organization/<uuid:pk>/", views.editOrganization, name="edit_organization"),
    # path('plan/', views.planView, name='plan'),

]