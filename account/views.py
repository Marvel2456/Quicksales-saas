from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from django.utils import timezone
from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import SetPasswordForm
from .models import CustomUser, ActivityLog, Branch, Organization, Notification
from subscriptions.models import Subscription, Plan
from .forms import *
from django.db import transaction
from django.contrib.auth.decorators import login_required
from .decorators import role_required, check_branch_limit
from ims.models import Sale, SalesItem, Inventory
from django.core.paginator import Paginator
from django.conf import settings
from .emails import send_welcome_email, send_verification_email, get_protocol, send_password_reset_email
from django.http import HttpResponse
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from .tasks import deactivate_subscription
from django.utils.timezone import make_aware

# Create your views here.


class OwnerRegisterView(View):
    def get(self, request):
        form = OwnerRegisterForm()
        return render(request, 'account/register.html', {'form': form})

    def post(self, request):
        form = OwnerRegisterForm(request.POST, request.FILES)

        if not form.is_valid():
            print(form.errors)

        if form.is_valid():
            with transaction.atomic():
                trial_start = timezone.now()
                trial_end = timezone.now() + timedelta(days=7)
                # Create organization
                organization = Organization.objects.create(
                    name=form.cleaned_data['organization_name'],
                    business_type = form.cleaned_data['business_type'],
                    country=form.cleaned_data['organization_country'],
                    logo=form.cleaned_data.get('organization_logo'),
                    brand_color=form.cleaned_data.get('brand_color', '#007bff'),
                    trial_start=trial_start,
                    trial_end=trial_end,
                    is_active=True
                )

                # Create default branch
                branch = Branch.objects.create(
                    organization=organization,
                    name=form.cleaned_data['branch_name'],
                    address=form.cleaned_data['branch_address']
                )

                # Assign free plan
                free_plan = Plan.objects.filter(price=0).first()
                subscription = Subscription.objects.create(
                    organization=organization,
                    plan=free_plan,
                    start_date=trial_start,
                    end_date=trial_end,
                    is_active=True
                )

                # Schedule deactivation at trial_end (Celery)
                deactivate_subscription.apply_async(
                    args=[str(subscription.id)],
                    eta=trial_end
                )




                # Create user
                user = form.save(commit=False)
                user.organization = organization
                user.role = 'owner'
                user.branch = branch
                user.set_password(form.cleaned_data['password1'])
                user.is_active = False
                user.save()
                # Assign the user to the organization and branch
                organization.owned_by = user
                organization.save()

                # Log the activity
                ActivityLog.objects.create(
                    staff=user,
                    organization=organization,
                    branch=organization.branch_set.first(),
                    activity='Owner registration completed'
                )

                # Generate subdomain login URL
                # login_url = f"http://{organization.slug}.lvh.me:8000/login/"


                
                # Send email verification
                send_verification_email(user, organization)
                messages.success(request, 'Registration successful! Please check your email to verify your account.')
                return redirect("login")


        return render(request, 'account/register.html', {'form': form})


def verifyEmail(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        if not user.is_active:
            user.is_active = True
            user.save()

            # generate subdomain login URL
            protocol = get_protocol()
            login_url = f"{protocol}://{user.organization.slug}.{settings.DOMAIN}/account/login/"

            # Send welcome email after verification
            send_welcome_email(user, login_url)

        messages.success(request, "Email verified successfully. You can now log in.")
        return redirect('login')
    else:
        return HttpResponse("Invalid or expired verification link.", status=400)

def loginUser(request):
    organization = request.organization
    
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        user = authenticate(request, email=email, password=password)

        if user is not None:
            if not user.is_active:
                messages.error(request, 'Account is inactive. Please contact support.')
                return redirect('login')

            login(request, user)
            log_org = user.organization or organization
            log_branch = user.branch
            if log_branch is None and log_org is not None:
                log_branch = log_org.branch_set.first()

            ActivityLog.objects.create(
                staff=user,
                organization=log_org,
                branch=log_branch,
                activity='Login successful'
            )

            # Create notification for owner when staff members log in
            if user.role in ['manager', 'sales'] and organization:
                owner = organization.owned_by
                if owner and owner != user:
                    # Create login notification for owner
                    login_message = f"{user.get_full_name() or user.email} ({user.role}) logged in"
                    if user.branch:
                        login_message += f" at {user.branch.name} branch"

                    Notification.objects.create(
                        user=owner,
                        message=login_message,
                        notification_type='info',
                        is_read=False
                    )

            messages.success(request, f'Welcome {user.get_full_name()}')

            if user.role == 'owner':
                return redirect('index')
            elif user.role in ['manager', 'sales']:
                if user.branch:
                    return redirect('branchdash', pk=user.branch.id)
                else:
                    messages.error(request, 'You are not assigned to a branch yet.')
                    return redirect('login')
            else:
                messages.warning(request, 'Your role is not recognized.')
                return redirect('login')

        else:
            messages.error(request, 'Invalid email or password.')

    return render(request, 'account/login.html')


def logoutUser(request):
    logout(request)
    
    return redirect('login')


def forgot_password(request):
    form = PasswordResetRequestForm()

    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user = CustomUser.objects.filter(email__iexact=email, is_active=True).first()

            if user:
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                protocol = get_protocol()

                domain = request.get_host()
                if settings.ENV == 'production' and user.organization and settings.DOMAIN:
                    domain = f"{user.organization.slug}.{settings.DOMAIN}"

                reset_link = f"{protocol}://{domain}/account/reset-password/{uid}/{token}/"
                send_password_reset_email(user, reset_link)

            messages.success(
                request,
                'If an account with that email exists, a reset link has been sent.'
            )
            return redirect('password_reset_sent')

    return render(request, 'account/forgot_password.html', {'form': form})


def password_reset_sent(request):
    return render(request, 'account/password_reset_sent.html')


def reset_password(request, uidb64, token):
    user = None
    validlink = False

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        validlink = True

    if not validlink:
        return render(
            request,
            'account/password_reset_confirm.html',
            {'validlink': False, 'form': None}
        )

    if request.method == 'POST':
        form = PasswordResetConfirmForm(user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your password has been reset. Please log in.')
            return redirect('password_reset_complete')
    else:
        form = PasswordResetConfirmForm(user)

    return render(
        request,
        'account/password_reset_confirm.html',
        {'validlink': True, 'form': form}
    )


def password_reset_complete(request):
    return render(request, 'account/password_reset_complete.html')

@login_required(login_url='login')
@check_branch_limit
def createBranch(request):
    organization = request.user.organization
    if not organization:
        messages.error(request, 'You do not belong to any organization.')
        return redirect('login')
    
    branch = Branch.objects.filter(organization=organization).all()
    form = CreateBranchForm()

    if request.method == 'POST':
        form = CreateBranchForm(request.POST)
        if form.is_valid():
            new_branch = form.save(commit=False)
            new_branch.organization = organization
            new_branch.save()
            messages.success(request, 'Branch Created Successfully')

            # Notify owner about new branch creation
            owner = organization.owned_by
            if owner and owner != request.user:
                Notification.objects.create(
                    user=owner,
                    message=f"New branch created: {new_branch.name}",
                    notification_type='success',
                    is_read=False
                )
            return redirect('branch')

    context = {
        'branch':branch,
        'form':form
    }

    return render(request, 'account/branch.html', context)

@login_required(login_url='login')
def editBranch(request):
    if request.method == 'POST':
        organization = request.user.organization
        if not organization:
            messages.error(request, 'You do not belong to any organization.')
            return redirect('login')

        branch = get_object_or_404(Branch, id=request.POST.get('id'), organization=organization)
        form = EditBranchForm(request.POST, instance=branch)
        if form.is_valid():
            form.save()
            messages.success(request, 'Successfully Updated')
            return redirect('branch')
    return redirect('branch')
            

# def edit_branch(request, pk):
#     organization = request.user.organization
#     branch = get_object_or_404(Branch, id=pk, organization=organization)

#     if request.method == 'POST':
#         form = CreateBranchForm(request.POST, instance=branch)
#         if form.is_valid():
#             form.save()
#             return HttpResponse(
#                 f'<div class="alert alert-success">Branch <strong>{branch.name}</strong> updated!</div>'
#             )
#     else:
#         form = CreateBranchForm(instance=branch)

#     return render(request, 'account/editbranch.html', {'form': form, 'branch': branch})

@login_required(login_url='login')
def deleteBranch(request):
    if request.method == 'POST':
        organization = request.user.organization
        if not organization:
            messages.error(request, 'You do not belong to any organization.')
            return redirect('login')

        branch = get_object_or_404(Branch, id=request.POST.get('id'), organization=organization)
        branch.delete()
        messages.success(request, 'Successfully Deleted')
        return redirect('branch')
    return redirect('branch')

# @login_required(login_url='login')
# def branchView(request, pk):
#     branch = Branch.objects.get(id=pk)
    
#     context = {
#         'branch':branch,
#     }
#     return render(request, 'account/branch_list.html', context)


# def staffPosView(request, pk):
#     pos = Pos.objects.get(id = pk)
#     staff = CustomUser.objects.filter(pos_id = pk)

#     context = {
#         'pos':pos,
#         'staff':staff
#     }
#     return render(request, 'account/pos_staff.html', context)

# def posSaleView(request, pk):
#     pos = Pos.objects.get(id=pk)
#     sale = Sale.objects.filter(staff_id = pk)
#     start_date_contains = request.GET.get('start_date')
#     end_date_contains = request.GET.get('end_date')

#     if start_date_contains != '' and start_date_contains is not None:
#         sale = sale.filter(date_updated__gte=start_date_contains)

#     if end_date_contains != '' and end_date_contains is not None:
#         sale = sale.filter(date_updated__lt=end_date_contains)
    
    
#     total_profits = sum(sale.values_list('total_profit', flat=True))

#     context = {
#         'pos':pos,
#         'sale':sale,
#         'total_profits':total_profits
#     }
#     return render(request, 'account/pos_sale.html', context)



@login_required(login_url='login')
def accountView(request):
    organization = request.user.organization
    subscription = Subscription.objects.filter(organization=organization).order_by('-end_date').first()
    plan = subscription.plan if subscription else None

    context = {
        'organization': organization,
        'subscription': subscription,
        'plan': plan,
    }
    return render(request, 'account/account.html', context)


@login_required(login_url='login')
def notifications_view(request):
    qs = request.user.notifications.all().order_by('-created_at')
    paginator = Paginator(qs, 20)
    page = request.GET.get('page')
    notifications = paginator.get_page(page)

    context = {
        'notifications': notifications
    }
    return render(request, 'account/notifications.html', context)


@login_required(login_url='login')
def change_password(request):
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        # Verify current password
        if not request.user.check_password(current_password):
            messages.error(request, "Current password is incorrect.")
            return redirect('account')
        
        # Check if new passwords match
        if new_password != confirm_password:
            messages.error(request, "New passwords do not match.")
            return redirect('account')
        
        # Check password length
        if len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return redirect('account')
        
        # Set the new password
        request.user.set_password(new_password)
        # Clear must_change_password flag if set
        if request.user.must_change_password:
            request.user.must_change_password = False
        request.user.save()
        
        # Important: Update the session to prevent logout
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, request.user)
        
        messages.success(request, "Your password has been changed successfully.")
        return redirect('account')
    
    return redirect('account')


@login_required(login_url='login')
def force_password_change(request):
    """
    Force users to change their password on first login.
    This view is accessible even when must_change_password is True.
    """
    # If user doesn't need to change password, redirect to dashboard
    if not request.user.must_change_password:
        return redirect('dashboard')
    
    if request.method == 'POST':
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        
        # Check if passwords match
        if new_password1 != new_password2:
            messages.error(request, "Passwords do not match.")
            return render(request, 'account/force_password_change.html')
        
        # Check password length
        if len(new_password1) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, 'account/force_password_change.html')
        
        # Set the new password
        request.user.set_password(new_password1)
        request.user.must_change_password = False
        request.user.save()
        
        # Important: Update the session to prevent logout
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, request.user)
        
        # Log the activity
        ActivityLog.objects.create(
            staff=request.user,
            organization=request.user.organization,
            branch=request.user.branch,
            activity='Password changed on first login'
        )
        
        messages.success(request, "Your password has been changed successfully. Welcome to Quicksales!")
        return redirect('dashboard')
    
    return render(request, 'account/force_password_change.html')


@login_required(login_url='login')
def update_profile(request):
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('account')

    user = request.user
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    phone_number = request.POST.get('phone_number', '').strip()

    user.first_name = first_name or user.first_name
    user.last_name = last_name or user.last_name
    user.phone_number = phone_number or None

    # Handle profile picture upload
    if 'profile_picture' in request.FILES:
        profile_picture = request.FILES['profile_picture']
        # Delete old picture if exists
        if user.profile_picture:
            user.profile_picture.delete(save=False)
        user.profile_picture = profile_picture

    user.save()
    messages.success(request, "Profile updated successfully.")
    return redirect('account')


@role_required(roles=['owner'])
@login_required(login_url='login')
def update_organization_branding(request):
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('settings')

    organization = request.user.organization
    if not organization:
        messages.error(request, "Organization not found.")
        return redirect('settings')

    # Handle logo upload
    if 'logo' in request.FILES:
        logo = request.FILES['logo']
        # Delete old logo if exists
        if organization.logo:
            organization.logo.delete(save=False)
        organization.logo = logo

    # Handle brand color
    brand_color = request.POST.get('brand_color', '').strip()
    if brand_color and brand_color.startswith('#'):
        organization.brand_color = brand_color

    organization.save()
    messages.success(request, "Organization branding updated successfully.")
    return redirect('settings')


@login_required(login_url='login')
def delete_notification(request, pk):
    notification = get_object_or_404(Notification, id=pk, user=request.user)
    if request.method == 'POST':
        notification.delete()
        messages.success(request, 'Notification deleted')
    return redirect('notifications')


@login_required(login_url='login')
def mark_notification_read(request, pk):
    """Mark a single notification as read"""
    notification = get_object_or_404(Notification, id=pk, user=request.user)
    notification.is_read = True
    notification.save()
    return redirect('notifications')


@login_required(login_url='login')
def mark_all_notifications_read(request):
    """Mark all unread notifications as read"""
    if request.method == 'POST':
        request.user.notifications.filter(is_read=False).update(is_read=True)
        messages.success(request, 'All notifications marked as read')
    return redirect('notifications')







# @role_required(roles=['owner'])
# @login_required
# def planView(request):
#     organization = request.user.organization
    
#     # Only fetch active subscription
#     subscription = (
#     Subscription.objects
#     .filter(organization=organization, is_active=True, end_date__gte=timezone.now())
#     .order_by('-end_date')
#     .first()
#     )

    
#     plan = subscription.plan if subscription else None
#     plans = Plan.objects.all()

#     context = {
#         'organization': organization,
#         'subscription': subscription,
#         'plan': plan,
#         'plans': plans,
#     }
#     return render(request, 'account/settings.html', context)


@login_required(login_url='login')
def session_check(request):
    """Check if user's session is still valid (for debugging idle timeout)"""
    from django.http import JsonResponse
    from datetime import datetime

    if request.user.is_authenticated:
        # Refresh session expiry on active use
        request.session.modified = True
        request.session.set_expiry(600)
        return JsonResponse({
            'authenticated': True,
            'user': request.user.email,
            'session_key': request.session.session_key,
            'expiry_seconds': request.session.get_expiry_age(),
            'timestamp': datetime.now().isoformat()
        })

    return JsonResponse({
        'authenticated': False,
        'timestamp': datetime.now().isoformat()
    }, status=401)
