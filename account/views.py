from datetime import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from .models import CustomUser, ActivityLog, Branch
from .forms import CreateBranchForm, EditBranchForm
from .decorators import for_admin, for_sub_admin
from ims.models import Sale, SalesItem, Inventory
from django.core.paginator import Paginator
# Create your views here.

def loginUser(request):
    if request.method =='POST':
        username = request.POST.get('email')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        

        # if user is not None and user.is_subscribed==False:
        #     messages.info(request, f'Subscription has expired kindly renew to continue')
        #     return redirect('login')
        if user is not None :
            if user.is_active and user.is_admin:
                login(request, user)
                ActivityLog.objects.create(staff=user,
                login_id = datetime.now().timestamp(),
                timestamp = datetime.now()
                ).save()
                messages.success(request, f'Welcome {user.username}')
                return redirect('index')
            elif user.is_active and user.is_sub_admin or user.is_active and user.is_work_staff:
                login(request, user)
                ActivityLog.objects.create(staff=user,
                login_id = datetime.now().timestamp(),
                timestamp = datetime.now()
                ).save()
                messages.success(request, f'Welcome {user.username}')
                return redirect('dashboard')
        else:
             messages.info(request, 'Username or Password is not correct')

    return render(request, 'account/login.html')


def logoutUser(request):
    logout(request)
    
    return redirect('login')

def createBranch(request):
    branch = Branch.objects.all()
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

def editBranch(request):
    if request.method == 'POST':
        branch = Branch.objects.get(id = request.POST.get('id'))
        if branch != None:
            form = EditBranchForm(request.POST, instance = branch)
            if form.is_valid():
                form.save()
                messages.success(request, 'Successfully Updated')
                return redirect('branch')

def deleteBranch(request):
    if request.method == 'POST':
        branch = Branch.objects.get(id = request.POST.get('id'))
        if branch != None:
            branch.delete()
            messages.success(request, 'Successfully Deleted')
            return redirect('branch')

def branchView(request, pk):
    branch = Branch.objects.get(id=pk)
    # pos = Pos.objects.filter(branch_id = pk)

    context = {
        'branch':branch,
        # 'pos':pos,
    }
    return render(request, 'account/branch_list.html', context)


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




