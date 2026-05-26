from django.urls import path
from . import views
from .views import OwnerRegisterView
from . import org_views

urlpatterns = [
    path('login/', views.loginUser, name='login'),
    path('resend-verification/', views.resend_verification_email, name='resend_verification_email'),
    path('logout/', views.logoutUser, name='logout'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/sent/', views.password_reset_sent, name='password_reset_sent'),
    path('reset-password/<uidb64>/<token>/', views.reset_password, name='reset_password'),
    path('reset-password/complete/', views.password_reset_complete, name='password_reset_complete'),
    path('branch/', views.createBranch, name='branch'),
    path('editbranch/', views.editBranch, name='editbranch'),
    path('deletebranch/', views.deleteBranch, name='deletebranch'),
    # path('branchview/<str:pk>/', views.branchView, name='branchview'),
    # path('editbranch/<uuid:pk>/', views.edit_branch, name='edit_branch'),
    path('register/', OwnerRegisterView.as_view(), name='register'),
    path('verify-email/<uidb64>/<token>/', views.verifyEmail, name='verify_email'),
    path('api/check-email/', views.check_email, name='check_email'),
    path('account/', views.accountView, name='account'),
    path('account/update-profile/', views.update_profile, name='update_profile'),
    path('account/change-password/', views.change_password, name='change_password'),
    path('account/force-password-change/', views.force_password_change, name='force_password_change'),
    path('settings/update-branding/', views.update_organization_branding, name='update_organization_branding'),
    # Notifications
    path('notifications/', views.notifications_view, name='notifications'),
    path('notifications/page/', views.notifications_page, name='notifications_page'),
    path('notifications/<uuid:pk>/delete/', views.delete_notification, name='notification_delete'),
    path('notifications/<uuid:pk>/mark-read/', views.mark_notification_read, name='notification_mark_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='notifications_mark_all_read'),
    path('api/session-check/', views.session_check, name='session_check'),
    # Organization Switching
    path('api/organizations/', org_views.user_organizations, name='user_organizations'),
    path('organizations/select/', org_views.select_organization, name='select_organization'),
    path('organizations/<str:org_id>/switch/', org_views.switch_organization, name='switch_organization'),
    # path('settings/', views.settingsView, name='settings'),
    # path("settings/edit_organization/<uuid:pk>/", views.editOrganization, name="edit_organization"),
    # path('plan/', views.planView, name='plan'),

]