from datetime import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from .models import CustomUser, LoggedIn, Pos, Branch, Shop
from .forms import CreateBranchForm, EditBranchForm, CreatePosForm, EditPosForm
from .decorators import for_admin, for_sub_admin, is_unsubscribed
from ims.models import Sale, SalesItem, Inventory
from django.core.paginator import Paginator
# Create your views here.

def loginUser(request):
    # branch = Branch.objects.get(id)
    if request.method =='POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        

        if user is not None and user.is_subscribed==False:
            messages.info(request, f'Subscription has expired kindly renew to continue')
            return redirect('login')
        elif user is not None and user.is_subscribed==True:
            if user.is_active and user.is_admin:
                login(request, user)
                LoggedIn.objects.create(staff=user,
                login_id = datetime.now().timestamp(),
                timestamp = datetime.now()
                ).save()
                messages.success(request, f'Welcome {user.username}')
                return redirect('index')
            elif user.is_active and user.is_sub_admin or user.is_active and user.is_work_staff:
                login(request, user)
                LoggedIn.objects.create(staff=user,
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
    pos = Pos.objects.filter(branch_id = pk)

    context = {
        'branch':branch,
        'pos':pos,
    }
    return render(request, 'account/branch_list.html', context)


def staffPosView(request, pk):
    pos = Pos.objects.get(id = pk)
    staff = CustomUser.objects.filter(pos_id = pk)

    context = {
        'pos':pos,
        'staff':staff
    }
    return render(request, 'account/pos_staff.html', context)

def posSaleView(request, pk):
    pos = Pos.objects.get(id=pk)
    sale = Sale.objects.filter(staff_id = pk)
    start_date_contains = request.GET.get('start_date')
    end_date_contains = request.GET.get('end_date')

    if start_date_contains != '' and start_date_contains is not None:
        sale = sale.filter(date_updated__gte=start_date_contains)

    if end_date_contains != '' and end_date_contains is not None:
        sale = sale.filter(date_updated__lt=end_date_contains)
    
    
    total_profits = sum(sale.values_list('total_profit', flat=True))

    context = {
        'pos':pos,
        'sale':sale,
        'total_profits':total_profits
    }
    return render(request, 'account/pos_sale.html', context)


def terminal(request):
    pos = Pos.objects.all()
    paginator = Paginator(Pos.objects.all(), 15)
    page = request.GET.get('page')
    pos_page = paginator.get_page(page)
    nums = "a" *pos_page.paginator.num_pages
    pos_contains = request.GET.get('pos')

    if pos_contains != '' and pos_contains is not None:
        pos_page = pos.filter(pos_name__icontains=pos_contains)

    form = CreatePosForm()
    if request.method == 'POST':
        form = CreatePosForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Pos Created Successfully')
            return redirect('pos')

    context = {
        'pos':pos,
        'pos_page':pos_page,
        'nums':nums,
        'form':form
    }
    return render(request, 'account/pos.html', context)

def posView(request, pk):
    pos = Pos.objects.get(id=pk)
    staff = CustomUser.objects.filter(pos_id = pk)
    sale = Sale.objects.filter(staff_id = pk)

    context = {
        'pos':pos,
        'staff':staff,
        'sale':sale
    }
    return render(request, 'account/pos_list.html', context)

def editPos(request):
    if request.method == 'POST':
        pos = Pos.objects.get(id = request.POST.get('id'))
        if pos != None:
            form = EditPosForm(request.POST, instance=pos)
            if form.is_valid():
                form.save()
                messages.success(request, 'Successfully Updated')
                return redirect('pos')


def deletePos(request):
    if request.method == 'POST':
        pos = Pos.objects.get(id = request.POST.get('id'))
        if pos != None:
            pos.delete()
            messages.success(request, 'Successfully Deleted')
            return redirect('pos')