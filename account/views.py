from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from django.utils import timezone
from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import SetPasswordForm
from .models import CustomUser, ActivityLog, Branch, Organization, Notification, OrganizationMembership
from subscriptions.models import Subscription, Plan
from .forms import *
from django.db import transaction
from django.contrib.auth.decorators import login_required
from .decorators import role_required, check_branch_limit
from ims.models import Sale, SalesItem, Inventory
from django.core.paginator import Paginator
from django.conf import settings
from .emails import get_protocol
from .utils import get_request_branch, get_request_org_role, get_request_organization
from django.http import HttpResponse, JsonResponse
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from .tasks import (
    deactivate_subscription,
    task_send_verification_email,
    task_send_welcome_email,
    task_send_password_reset_email,
)
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
            return render(request, 'account/register.html', {'form': form})

        # Extract cleaned data
        email = form.cleaned_data['email']
        first_name = form.cleaned_data['first_name']
        last_name = form.cleaned_data['last_name']
        phone_number = form.cleaned_data.get('phone_number', '')
        password = form.cleaned_data.get('password1')
        
        # Check if user already exists
        try:
            existing_user = CustomUser.objects.get(email=email)
            user_exists = True
        except CustomUser.DoesNotExist:
            user_exists = False
            existing_user = None
        
        # Block duplicate organization names for the same owner
        organization_name = form.cleaned_data['organization_name']
        if user_exists and existing_user:
            duplicate = Organization.objects.filter(
                owned_by=existing_user,
                name__iexact=organization_name
            ).exists()
            if duplicate:
                messages.error(request, f'You already own an organization called "{organization_name}". Please choose a different name.')
                return render(request, 'account/register.html', {'form': form})
        
        with transaction.atomic():
            trial_start = timezone.now()
            trial_end = timezone.now() + timedelta(days=7)
            
            # Create organization
            organization = Organization.objects.create(
                name=form.cleaned_data['organization_name'],
                business_type=form.cleaned_data['business_type'],
                country=form.cleaned_data.get('organization_country', ''),
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

            if user_exists:
                # User already exists - add them to this new organization
                user = existing_user
                
                # Update user's default org/branch if they don't have one
                if not user.organization:
                    user.organization = organization
                    user.branch = branch
                    user.save()
                
                # Set organization owner
                organization.owned_by = user
                organization.save()
                
                # Create membership for this organization
                from account.models import OrganizationMembership
                OrganizationMembership.objects.create(
                    user=user,
                    organization=organization,
                    branch=branch,
                    role='owner',
                    is_active=True
                )
                
                # Log the activity
                ActivityLog.objects.create(
                    staff=user,
                    organization=organization,
                    branch=branch,
                    activity=f'Added as owner of new organization: {organization.name}'
                )
                
                # Send verification email for the new organization
                task_send_verification_email.delay(user.id, organization.id)
                
                messages.success(
                    request,
                    f'Organization created successfully! Please check your email to verify your account for {organization.name}.'
                )
            else:
                # Create new user
                user = CustomUser.objects.create(
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    phone_number=phone_number,
                    organization=organization,
                    role='owner',
                    branch=branch,
                    is_active=False
                )
                user.set_password(password)
                user.save()
                
                # Assign the user to the organization
                organization.owned_by = user
                organization.save()
                
                # Create membership
                from account.models import OrganizationMembership
                OrganizationMembership.objects.create(
                    user=user,
                    organization=organization,
                    branch=branch,
                    role='owner',
                    is_active=True
                )

                # Log the activity
                ActivityLog.objects.create(
                    staff=user,
                    organization=organization,
                    branch=organization.branch_set.first(),
                    activity='Owner registration completed'
                )

                # Send email verification
                task_send_verification_email.delay(user.id, organization.id)
                messages.success(
                    request,
                    'Registration successful! Please check your email to verify your account.'
                )
            
            return redirect("login")


def verifyEmail(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        # Get the organization from the request (subdomain)
        organization = get_request_organization(request)
        
        # If user is not active, activate them
        if not user.is_active:
            user.is_active = True
            user.save()

        # Always send welcome email for the organization they're verifying
        if organization:
            protocol = get_protocol()
            login_url = f"{protocol}://{organization.slug}.{settings.DOMAIN}/account/login/"
            task_send_welcome_email.delay(user.id, login_url)

        messages.success(request, "Email verified successfully. You can now log in.")
        return redirect('login')
    else:
        return HttpResponse("Invalid or expired verification link.", status=400)

def check_email(request):
    email = request.GET.get('email', '').strip()
    if email:
        exists = CustomUser.objects.filter(email__iexact=email).exists()
        return JsonResponse({'exists': exists})
    return JsonResponse({'exists': False})

def loginUser(request):
    """Multi-step login: email -> organization select -> password"""
    organization = request.organization
    
    # Step 2: Organization selection (check this BEFORE step 1)
    if request.method == 'POST' and 'organization_id' in request.POST:
        email = request.session.get('login_email')
        org_id = request.POST.get('organization_id')
        
        if not email or not org_id:
            messages.error(request, 'Session expired. Please start over.')
            return redirect('login')
        
        try:
            user = CustomUser.objects.get(email__iexact=email)
            # Verify user has access to this organization
            membership = user.memberships.filter(
                organization_id=org_id,
                is_active=True,
            ).select_related('organization').first()
            if not membership:
                raise OrganizationMembership.DoesNotExist
            
            request.session['selected_org_id'] = org_id
            request.session.modified = True
            
            # Redirect to password page
            return render(request, 'account/login_password.html', {
                'email': email,
                'organization': membership.organization
            })
        except (CustomUser.DoesNotExist, OrganizationMembership.DoesNotExist):
            messages.error(request, 'Unauthorized access.')
            return redirect('login')
    
    # Step 3: Password submission
    if request.method == 'POST' and 'password' in request.POST:
        email = request.session.get('login_email')
        org_id = request.session.get('selected_org_id')
        is_legacy = request.session.get('is_legacy_user', False)
        password = request.POST.get('password')
        
        if not email:
            return render(request, 'account/login.html', {
                'error': 'Session expired. Please start over.'
            })
        
        user = authenticate(request, email=email, password=password)
        
        if user is not None:
            if not user.is_active:
                messages.error(request, 'Account is inactive. Please contact support.')
                return redirect('login')
            
            login(request, user)
            
            # Handle legacy vs multi-org users
            role_for_session = None
            if is_legacy:
                # Legacy user - use FK fields
                log_org = user.organization
                log_branch = user.branch
                role_for_session = user.role
                
                # Set session for consistency
                if log_org:
                    request.session['active_organization_id'] = str(log_org.id)
                if role_for_session == 'owner':
                    request.session['active_branch_id'] = None
                    request.session['active_branch_name'] = None
                    log_branch = None
                elif log_branch:
                    request.session['active_branch_id'] = str(log_branch.id)
            else:
                # Multi-org user - get membership
                try:
                    membership = user.memberships.filter(
                        organization_id=org_id,
                        is_active=True,
                    ).select_related('organization', 'branch').first()
                    if not membership:
                        raise OrganizationMembership.DoesNotExist
                    log_org = membership.organization
                    log_branch = membership.branch
                    role_for_session = membership.role
                    
                    # Set session context for the selected organization AND branch
                    request.session['active_organization_id'] = str(log_org.id) if log_org else None
                    if role_for_session == 'owner':
                        request.session['active_branch_id'] = None
                        request.session['active_branch_name'] = None
                        log_branch = None
                    else:
                        request.session['active_branch_id'] = str(log_branch.id) if log_branch else None
                except:
                    log_org = user.organization or organization
                    log_branch = user.branch
                    role_for_session = user.role
                    
                    if log_org:
                        request.session['active_organization_id'] = str(log_org.id)
                    if role_for_session == 'owner':
                        request.session['active_branch_id'] = None
                        request.session['active_branch_name'] = None
                        log_branch = None
                    elif log_branch:
                        request.session['active_branch_id'] = str(log_branch.id)
            
            if log_branch is None and log_org is not None and role_for_session != 'owner':
                log_branch = log_org.branch_set.first()

            request.session.modified = True

            # Also set in request context for immediate use
            request.organization = log_org
            request.branch = log_branch

            ActivityLog.objects.create(
                staff=user,
                organization=log_org,
                branch=log_branch,
                activity='Login successful'
            )

            # Subscription expiry check for sales/manager
            subscription = Subscription.objects.filter(organization=log_org, is_active=True).order_by('-end_date').first()
            expired = False
            if subscription:
                if subscription.end_date and subscription.end_date < timezone.now():
                    expired = True
            else:
                expired = True

            # Create notification for owner when staff members log in
            if role_for_session in ['manager', 'sales'] and log_org:
                owner = log_org.owned_by
                if owner and owner != user:
                    login_message = f"{user.get_full_name() or user.email} ({role_for_session}) logged in"
                    if log_branch:
                        login_message += f" at {log_branch.name} branch"
                    Notification.objects.create(
                        user=owner,
                        message=login_message,
                        notification_type='info',
                        organization=log_org,
                        is_read=False
                    )

            # Clear session login data
            if 'login_email' in request.session:
                del request.session['login_email']
            if 'selected_org_id' in request.session:
                del request.session['selected_org_id']
            if 'is_legacy_user' in request.session:
                del request.session['is_legacy_user']
            request.session.modified = True

            messages.success(request, f'Welcome {user.get_full_name()}')

            # For multi-org users, use the membership role, not the user's global role
            if is_legacy:
                redirect_role = user.role
            else:
                # Get role from membership for the selected organization
                try:
                    membership = user.memberships.filter(
                        organization_id=org_id,
                        is_active=True,
                    ).first()
                    redirect_role = membership.role if membership else user.role
                except:
                    redirect_role = user.role  # Fallback to user role

            # Redirect logic
            if redirect_role == 'owner':
                # Owners see the list of all branches in their organization (branchdash.html)
                return redirect('index')
            elif redirect_role in ['manager', 'sales']:
                if expired:
                    messages.error(request, 'Organization subscription has expired. Contact admin for a sales or manager role.')
                    return redirect('login')
                if log_branch:
                    return redirect('branchdash', pk=log_branch.id)
                else:
                    messages.error(request, 'You are not assigned to a branch yet.')
                    return redirect('login')
            else:
                messages.warning(request, 'Your role is not recognized.')
                return redirect('login')
        else:
            # Invalid password
            try:
                failed_user = CustomUser.objects.get(email__iexact=email)
                if is_legacy:
                    org_obj = failed_user.organization
                else:
                    try:
                        org_obj = failed_user.memberships.get(
                            organization_id=org_id, is_active=True
                        ).organization
                    except:
                        org_obj = None
            except CustomUser.DoesNotExist:
                org_obj = None
                    
            return render(request, 'account/login_password.html', {
                'email': email,
                'error': 'Invalid password. Please try again.',
                'organization': org_obj
            })
    
    # Step 1: Email submission
    if request.method == 'POST' and 'email' in request.POST:
        email = request.POST.get('email', '').strip()
        
        try:
            user = CustomUser.objects.get(email__iexact=email)
            # Get all active organizations for this user
            orgs = user.memberships.filter(is_active=True).select_related('organization')
            
            if orgs.count() == 0:
                # No memberships - check if user has legacy single-org setup
                if user.organization:
                    # Legacy single-organization user - go straight to password
                    request.session['login_email'] = email
                    request.session['is_legacy_user'] = True
                    request.session.modified = True
                    return render(request, 'account/login_password.html', {
                        'email': email,
                        'organization': user.organization
                    })
                else:
                    # User exists but has no active organizations
                    return render(request, 'account/login.html', {
                        'error': 'You do not have access to any organizations. Please contact support.',
                        'email': email
                    })
            elif orgs.count() == 1:
                # Only one organization - skip selector
                request.session['login_email'] = email
                request.session['selected_org_id'] = str(orgs.first().organization.id)
                request.session['is_legacy_user'] = False
                request.session.modified = True
                return render(request, 'account/login_password.html', {
                    'email': email,
                    'organization': orgs.first().organization
                })
            else:
                # Multiple organizations - show selector
                request.session['login_email'] = email
                request.session['is_legacy_user'] = False
                request.session.modified = True
                
                org_list = []
                for membership in orgs:
                    org_list.append({
                        'id': str(membership.organization.id),
                        'name': membership.organization.name,
                        'logo': membership.organization.logo.url if membership.organization.logo else None,
                        'role': membership.role,
                    })
                
                return render(request, 'account/login_org_select.html', {
                    'email': email,
                    'organizations': org_list,
                    'user': user
                })
        except CustomUser.DoesNotExist:
            return render(request, 'account/login.html', {
                'error': 'No account found with this email. Please check and try again.',
                'email': email
            })
    
    # Default: Show email entry form
    return render(request, 'account/login.html')


def logoutUser(request):
    logout(request)
    if request.GET.get('reason') == 'session_expired':
        messages.info(request, 'Your session expired. Please login again.')
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
                task_send_password_reset_email.delay(user.id, reset_link)

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
    organization = get_request_organization(request)
    if not organization:
        messages.error(request, 'You do not belong to any organization.')
        return redirect('login')
    
    branch = Branch.objects.filter(organization=organization).all()

    search_query = request.GET.get('branch', '').strip()
    if search_query:
        branch = branch.filter(name__icontains=search_query)

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
                    organization=organization,
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
        organization = get_request_organization(request)
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
        organization = get_request_organization(request)
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
    organization = get_request_organization(request)
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
    paginator = Paginator(qs, 15)
    page = request.GET.get('page')
    notifications = paginator.get_page(page)

    context = {
        'notifications': notifications
    }
    return render(request, 'account/notifications.html', context)


@login_required(login_url='login')
def notifications_page(request):
    """HTMX partial: returns one page of notification list items."""
    qs = request.user.notifications.all().order_by('-created_at')
    paginator = Paginator(qs, 15)
    page = request.GET.get('page', 1)
    notifications = paginator.get_page(page)
    return render(request, 'account/partials/notifications_page.html', {'notifications': notifications})


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

    form = SetPasswordForm(request.user, request.POST or None)
    form.fields['new_password1'].widget.attrs.update({
        'class': 'form-control',
        'placeholder': 'Enter new password',
        'autocomplete': 'new-password',
    })
    form.fields['new_password2'].widget.attrs.update({
        'class': 'form-control',
        'placeholder': 'Confirm new password',
        'autocomplete': 'new-password',
    })

    if request.method == 'POST':
        if form.is_valid():
            form.save()
            request.user.must_change_password = False
            request.user.save(update_fields=['must_change_password'])

            # Important: Update the session to prevent logout
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, request.user)

            # Log the activity
            ActivityLog.objects.create(
                staff=request.user,
                organization=get_request_organization(request),
                branch=get_request_branch(request),
                activity='Password changed on first login'
            )

            messages.success(request, "Your password has been changed successfully. Welcome to Quicksales!")
            return redirect('dashboard')

        messages.error(request, "Please correct the errors below.")

    return render(request, 'account/force_password_change.html', {'form': form})


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

    organization = get_request_organization(request)
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
