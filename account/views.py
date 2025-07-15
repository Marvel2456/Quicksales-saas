from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from django.utils import timezone
from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from .models import CustomUser, ActivityLog, Branch, Organization
from subscriptions.models import Subscription, Plan
from .forms import *
from django.db import transaction
from django.contrib.auth.decorators import login_required
from .decorators import role_required
from ims.models import Sale, SalesItem, Inventory
from django.core.paginator import Paginator
from django.conf import settings
from .emails import send_welcome_email, send_verification_email
from django.http import HttpResponse
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from .tasks import deactivate_subscription
from django.utils.timezone import make_aware

# Create your views here.


class OwnerRegisterView(View):
    def get(self, request):
        form = OwnerRegisterForm()
        return render(request, 'account/register.html', {'form': form})

    def post(self, request):
        form = OwnerRegisterForm(request.POST)

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

                # Schedule deactivation at trial_end
                deactivate_subscription.configure(
                    schedule_at=trial_end
                ).defer(
                    subscription_id=str(subscription.id)
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
            # login_url = f"http://{user.organization.slug}.lvh.me:8000/login/"
            login_url = f"http://{user.organization.slug}.{settings.DOMAIN}/login/"

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
            ActivityLog.objects.create(
                staff=user,
                organization=organization,
                branch=user.branch,
                activity={'Login successful'}
                
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

@login_required(login_url='login')
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
            form.save()
            messages.success(request, 'Branch Created Successfully')
            return redirect('branch')

    context = {
        'branch':branch,
        'form':form
    }

    return render(request, 'account/branch.html', context)

@login_required(login_url='login')
def editBranch(request):
    if request.method == 'POST':
        branch = Branch.objects.get(id = request.POST.get('id'))
        if branch != None:
            form = EditBranchForm(request.POST, instance = branch)
            if form.is_valid():
                form.save()
                messages.success(request, 'Successfully Updated')
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
        branch = Branch.objects.get(id = request.POST.get('id'))
        if branch != None:
            branch.delete()
            messages.success(request, 'Successfully Deleted')
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




