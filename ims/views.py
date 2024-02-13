from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from django.contrib import messages
from datetime import datetime, date
from .models import Category, Product, Sale, SalesItem, Inventory, ErrorTicket
from account.models import CustomUser, LoggedIn, Pos, Branch
from django.contrib.auth.decorators import login_required
from . forms import *
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
import csv
import json
from account.decorators import for_admin, for_staff, for_sub_admin
from django.template.loader import get_template
from xhtml2pdf import pisa




# Create your views here
@login_required(login_url=('login'))
# @is_unsubscribed

def branchDasboard(request):
    branch = Branch.objects.all()
    paginator = Paginator(Branch.objects.all(), 15)
    page = request.GET.get('page')
    branch_page = paginator.get_page(page)
    nums = "a" *branch_page.paginator.num_pages
    branch_contains_query = request.GET.get('branch')

    if branch_contains_query != '' and branch_contains_query is not None:
        branch_page = branch.filter(branch_name__icontains=branch_contains_query)

    context = {
        'branch':branch,
        'branch_page':branch_page,
        'nums':nums
    }
    return render(request, 'ims/branchdash.html', context)

@login_required(login_url=('login'))
# @is_unsubscribed
def dashboard(request, pk):
    branch = Branch.objects.get(id=pk)
    now = datetime.now()
    current_year = now.strftime("%Y")
    current_month = now.strftime("%m")
    current_day = now.strftime("%d")
    products = Product.objects.all()
    category = Category.objects.all()
    
    total_product = products.count()
    total_category = category.count()
    transaction = len(Sale.objects.filter(
        date_added__year=current_year,
        date_added__month = current_month,
        date_added__day = current_day,
        branch_id = pk
    ))
    today_sales = Sale.objects.filter(
        date_added__year=current_year,
        date_added__month = current_month,
        date_added__day = current_day,
        branch_id = pk
    ).all()
    total_sales = sum(today_sales.values_list('final_total_price',flat=True))
    # make graph for highest paid products per day
    today_profit = Sale.objects.filter(
        date_added__year=current_year,
        date_added__month = current_month,
        date_added__day = current_day,
        branch_id = pk
    ).all()
    total_profits = sum(today_profit.values_list('total_profit', flat=True))
    pending = ErrorTicket.objects.filter(status='Pending')
    inventory = Inventory.objects.filter(branch_id = branch).all()

    sale = Sale.objects.filter(branch_id = branch).order_by('-total_profit')[:7]
    item = SalesItem.objects.filter(branch_id = branch).order_by('-quantity')[:7]


    context = {
        'branch':branch,
        'pending':pending,
        'products':products,
        'category':category,
        'total_product':total_product,
        'total_category':total_category,
        'transaction':transaction,
        'total_sales':total_sales,
        'total_profits':total_profits,
        'sale':sale,
        'item':item,
        'inventory':inventory
    }
    return render(request, 'ims/index.html', context)

def staffDashboard(request):
    return render(request, 'ims/dashboard.html')

@login_required
# @is_unsubscribed
@for_admin

def branchReport(request):
    branch = Branch.objects.all()

    context = {
        'branch':branch
    }
    return render(request, 'ims/branchrep.html', context)

@login_required
# @is_unsubscribed
@for_admin
def report(request, pk):
    branch = Branch.objects.get(id=pk)
    now = datetime.now()
    start_date_contains = request.GET.get('start_date')
    end_date_contains = request.GET.get('end_date')
    sale = Sale.objects.filter(branch_id = pk)

    if start_date_contains != '' and start_date_contains is not None:
        sale = sale.filter(date_updated__gte=start_date_contains)

    if end_date_contains != '' and end_date_contains is not None:
        sale = sale.filter(date_updated__lt=end_date_contains)
    
    
    total_profits = sum(sale.values_list('total_profit', flat=True))
    

    context = {
        'branch':branch,
        'sale':sale,
        'total_profits':total_profits,
    }
    return render(request, 'ims/reports.html', context)

@login_required(login_url=('login'))
# @is_unsubscribed
@for_admin

def branchStore(request):
    inventory = Inventory.objects.all().order_by('branch')
    paginator = Paginator(Inventory.objects.all(), 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" *inventory_page.paginator.num_pages
    product_contains_query = request.GET.get('product')
    staff_contains_query = request.GET.get('branch')

    if product_contains_query != '' and product_contains_query is not None:
        inventory_page = inventory.filter(product__product_name__icontains=product_contains_query)

    if staff_contains_query != '' and staff_contains_query is not None:
        inventory_page = inventory.filter(branch__branch_name__icontains=staff_contains_query)

    context = {
        'inventory':inventory,
        'inventory_page':inventory_page,
        'nums':nums
    }
    return render(request, 'ims/branchstore.html', context)


@login_required
# @is_unsubscribed
@for_staff
def store(request):
    # branch = Branch.objects.get(id=pk)
    branch = request.user.branch
    inventory = Inventory.objects.filter(branch_id = branch).all()
    paginator = Paginator(Inventory.objects.all(), 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" *inventory_page.paginator.num_pages
    product_contains_query = request.GET.get('product')

    if product_contains_query != '' and product_contains_query is not None:
        inventory_page = inventory.filter(product__product_name__icontains=product_contains_query)


    context = {
        'branch':branch,
        'inventory':inventory,
        'inventory_page':inventory_page,
        'nums':nums
    }
    return render(request, 'ims/store.html', context)


@for_staff
@login_required
# @is_unsubscribed
def cart(request):
    # branch = Branch.objects.get(id=pk)
    
    
    if request.user.is_authenticated:
        staff = request.user
        branch = request.user.branch
        inventory = Inventory.objects.filter(branch_id = branch).all()
        sale , created = Sale.objects.filter(branch_id = branch).get_or_create(staff=staff, branch=branch, completed=False)
        items = sale.salesitem_set.all()
        
    context = {
        'branch':branch,
        'items':items,
        'sale':sale,
        'inventory':inventory
    }
    return render(request, 'ims/cart.html', context)


@for_staff
@login_required
# @is_unsubscribed
def checkout(request):
    # branch = Branch.objects.get(id=pk)
       
    if request.user.is_authenticated:
        staff = request.user
        branch = request.user.branch
        inventory = Inventory.objects.filter(branch_id = branch).all()
        sale , created = Sale.objects.filter(branch_id = branch).get_or_create(staff=staff, branch=branch, completed=False)
        items = sale.salesitem_set.all()
        form = PaymentForm()
        if request.method == 'POST':
            form = PaymentForm(request.POST or None, instance=sale)
            if form.is_valid():
                sale = form.save(commit=False)
                sale.save()
                messages.success(request, 'Payment Method Updated')
        
    context = {
        'branch':branch,
        'items':items,
        'sale':sale,
        'inventory':inventory,
    }
    return render(request, 'ims/checkout.html', context)


def updateCart(request):
    data = json.loads(request.body)
    inventoryId = data['inventoryId']
    action = data['action']
    print('inventory:', inventoryId)
    print('Action:', action)
   
    staff = request.user
    branch = request.user.branch.id
    inventory = Inventory.objects.filter(branch_id = branch).get(id=inventoryId)
    sale, created = Sale.objects.filter(branch_id = branch).get_or_create(staff=staff, branch_id=branch, completed=False)
    saleItem, created = SalesItem.objects.filter(branch_id = branch).get_or_create(sale=sale, branch_id=branch, inventory=inventory)

    if action == 'add':
        saleItem.quantity = (saleItem.quantity + 1)
    saleItem.save()

    if saleItem.quantity <= 0:
        saleItem.delete()

    context = {
        'branch':branch,
        'qty': sale.get_cart_items,
    }

    return JsonResponse(context, safe=False)


def updateQuantity(request):
    data = json.loads(request.body)
    input_value = int(data['val'])
    inventory_Id = data['invent_id']
    
    staff = request.user
    branch = request.user.branch.id
    inventory = Inventory.objects.filter(branch_id = branch).get(id=inventory_Id)
    sale, created = Sale.objects.filter(branch_id = branch).get_or_create(staff=staff, branch=branch, completed=False)
    saleItem, created = SalesItem.objects.filter(branch_id = branch).get_or_create(sale=sale, branch=branch, inventory=inventory)
    saleItem.quantity = input_value
    saleItem.save()

    if saleItem.quantity <= 0:
        saleItem.delete()

    context = {
        'branch':branch,
        'sub_total':saleItem.get_total,
        'final_total':sale.get_cart_total,
        'total_quantity':sale.get_cart_items,
    }

    return JsonResponse(context, safe=False)


def sale_complete(request, pk):
    branch = Branch.objects.get(id=pk)
    transaction_id = datetime.now().timestamp()
    data = json.loads(request.body)
   
    staff = request.user
    branch = request.user.branch.id
    sale, created = Sale.objects.filter(branch_id = pk).get_or_create(staff=staff, branch=branch, completed=False)
    sale.transaction_id = transaction_id
    total = float(data['payment']['total_cart'])
    sale.final_total_price = sale.get_cart_total
    sale.total_profit = sale.get_total_profit


    if total == sale.get_cart_total:
        sale.completed = True
    sale.save()


    messages.success(request, 'sale completed')

    context = {
        'branch':branch
    }

#   need to add shop in other to manage multiple shops and staffs per shop
    return JsonResponse(context, safe=False)

@login_required
# @is_unsubscribed
@for_admin    
def sales(request):
    sale = Sale.objects.all().order_by('-date_updated')
    paginator = Paginator(Sale.objects.all().order_by('-date_updated'), 10)
    page = request.GET.get('page')
    sale_page = paginator.get_page(page)
    nums = "a" *sale_page.paginator.num_pages
    start_date_contains = request.GET.get('start_date')
    end_date_contains = request.GET.get('end_date')
    branch_contains_query = request.GET.get('branch')

    if start_date_contains != '' and start_date_contains is not None:
        sale_page = sale.filter(date_updated__gte=start_date_contains)

    if end_date_contains != '' and end_date_contains is not None:
        sale_page = sale.filter(date_updated__lt=end_date_contains)

    if branch_contains_query != '' and branch_contains_query is not None:
        sale_page = sale.filter(branch__branch_name__icontains=branch_contains_query)

    context = {
        'sale':sale,
        'sale_page':sale_page,
        'nums':nums
    }
    return render(request, 'ims/sales.html', context)


def sale_pdf(request):
    sale = Sale.objects.all()

    template_path = 'ims/salepdf.html'
    context = {'sale': sale}
    # Create a Django response object, and specify content_type as pdf
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'filename="Sales_report.pdf"'
    # find the template and render it.
    template = get_template(template_path)
    html = template.render(context)

    # create a pdf
    pisa_status = pisa.CreatePDF(
       html, dest=response)
    # if error then show some funny view
    if pisa_status.err:
       return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response

@for_admin
def sale(request, pk):
    sale = Sale.objects.get(id=pk)

    context = {
        'sale':sale
    }
    return render(request, 'ims/sales_delete.html', context)

@for_admin
def sale_delete(request):
    if request.method == 'POST':
        sale = Sale.objects.get(id = request.POST.get('id'))
        if sale != None:
            sale.delete()
            messages.success(request, "Succesfully deleted")
            return redirect('sales')

@for_admin
def export_sales_csv(request):
    response = HttpResponse(content_type = 'text/csv')
    response['Content-Disposition']='attachment; filename = Sales History'+str(datetime.now())+'.csv'
    writer = csv.writer(response)
    writer.writerow(['Sales Rep', 'Trans Id', 'Date', 'Quantity', 'Total', 'Profit'])
    
    sale = Sale.objects.all()
    
    for sale in sale:
        writer.writerow([sale.staff, sale.transaction_id, sale.date_updated, sale.get_cart_items, sale.final_total_price, sale.total_profit])
    
    return response

@for_admin
def export_profit_csv(request, pk):
    branch = Branch.objects.get(id=pk)
    start_date_contains = request.GET.get('start_date')
    end_date_contains = request.GET.get('end_date')

    response = HttpResponse(content_type = 'text/csv')
    response['Content-Disposition']='attachment; filename = Profit History'+str(datetime.now())+'.csv'
    writer = csv.writer(response)
    writer.writerow(['Sales Rep', 'Trans Id', 'Date', 'Quantity', 'Total', 'Profit'])
    
    
    sale = Sale.objects.filter(branch_id = pk)

    if start_date_contains:
        sale = sale.filter(date_updated__gte=start_date_contains)

    if end_date_contains:
        sale = sale.filter(date_updated__lt=end_date_contains)

    total_profits = sum(sale.values_list('total_profit', flat=True))
    for sale in sale:
        writer.writerow([sale.staff, sale.transaction_id, sale.date_updated, sale.get_cart_items, sale.final_total_price, sale.total_profit])
        
    writer.writerow(['Total Profit'])
    if total_profits:
        writer.writerow([total_profits])
    
    
    return response
    

@for_staff
@login_required
# @is_unsubscribed
def reciept(request, pk):
    sale = Sale.objects.get(id = pk)
    salesitem = SalesItem.objects.filter(sale_id=sale).all()
    
    context = {
        'salesitem':salesitem,
        'sale':sale
    }
    return render(request, 'ims/reciept.html', context)


def profitData(request, pk):
    profits = []

    sale = Sale.objects.get(id = pk)
    items = sale.salesitem_set.all()

    for i in items:
        profits.append({i.get_profit:i.inventory.product.product_name})

    return JsonResponse(profits, safe=False)


#  only admin can create categories and products
@for_sub_admin
@login_required
# @is_unsubscribed
def product_category(request):
    products = Product.objects.all().order_by('-date_created')
    category = Category.objects.filter().all()
    paginator = Paginator(Product.objects.all(), 15)
    page = request.GET.get('page')
    products_page = paginator.get_page(page)
    nums = "a" *products_page.paginator.num_pages
    product_contains = request.GET.get('product_name')
    form = ProductForm()
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'successfully created')
            return redirect('products')

    if product_contains != '' and product_contains is not None:
        products_page = products.filter(product_name__icontains=product_contains)
        
    context = {
        'category':category,
        'form':form,
        'products':products,
        'products_page':products_page,
        'nums':nums
    }
    return render(request, 'ims/products.html', context)


@for_admin
def product(request, pk):
    products = Product.objects.get(id=pk)

    context = {
        'products':products
    } 
    return render(request, 'ims/modal_edit_product.html', context)


@for_admin
def edit_product(request):
    if request.method == 'POST':
        product = Product.objects.get(id = request.POST.get('id'))
        if product != None:
            form = EditProductForm(request.POST, instance=product)
            if form.is_valid():
                form.save()
                messages.success(request, 'successfully updated')
                return redirect('products')


@for_admin
def delete_product(request):
    if request.method == 'POST':
        product = Product.objects.get(id = request.POST.get('id'))
        if product != None:
            product.delete()
            messages.success(request, "Succesfully deleted")
            return redirect('products')


@login_required
# @is_unsubscribed
@for_sub_admin
def category_list(request):
    category = Category.objects.all()
    paginator = Paginator(Category.objects.all(), 3)
    page = request.GET.get('page')
    category_page = paginator.get_page(page)
    nums = "a" *category_page.paginator.num_pages
    category_contains = request.GET.get('category_name')
    form = CategoryForm()
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'successfully created')
            return redirect('category_list')
            
    if category_contains != '' and category_contains is not None:
        category_page = category.filter(category_name__icontains=category_contains)

    context = {
        'category':category,
        'form':form,
        'category_page':category_page,
        'nums':nums
    }
    return render(request, 'ims/category.html', context)


@for_admin
@login_required
# @is_unsubscribed
def category(request, pk):
    category = Category.objects.get(id=pk)

    context = {
        'category':category
    }
    return render(request, 'ims/edit_category', context)


@for_sub_admin
def edit_category(request):
    if request.method == 'POST':
        category = Category.objects.get(id = request.POST.get('id'))
        if category != None:
            form = EditCategoryForm(request.POST, instance=category)
            if form.is_valid():
                form.save()
                messages.success(request, 'successfully updated')
                return redirect('category_list')


@for_admin
def delete_category(request):
    if request.method == 'POST':
        category = Category.objects.get(id = request.POST.get('id'))
        if category != None:
            category.delete()
            messages.success(request, "Succesfully deleted")
            return redirect('category_list')

@for_admin
@login_required
# @is_unsubscribed
def branchInventory(request):
    inventory = Inventory.objects.all().order_by('branch')
    product = Product.objects.filter().all()
    branch = Branch.objects.filter().all()
    paginator = Paginator(Inventory.objects.all(), 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" *inventory_page.paginator.num_pages
    product_contains_query = request.GET.get('product')
    branch_contains_query = request.GET.get('branch')
    form = AdminCreateInventoryForm
    if request.method == "POST":
        form = AdminCreateInventoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'successfully created')
            return redirect('branchinv')

    if product_contains_query != '' and product_contains_query is not None:
        inventory_page = inventory.filter(product__product_name__icontains=product_contains_query)

    if branch_contains_query != '' and branch_contains_query is not None:
        inventory_page = inventory.filter(branch__branch_name__icontains=branch_contains_query)


    context = {
        'inventory':inventory,
        'product':product,
        'branch':branch,
        'form':form,
        'inventory_page':inventory_page,
        'nums':nums,

    }

    return render(request, 'ims/branch_inv.html', context)


@for_sub_admin
@login_required
# @is_unsubscribed
def inventory_list(request):
    branch = request.user.branch
    inventory = Inventory.objects.filter(branch_id = branch).all()
    product = Product.objects.filter().all()
    paginator = Paginator(Inventory.objects.filter(branch_id = branch).all(), 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" *inventory_page.paginator.num_pages
    product_contains_query = request.GET.get('product')
    form = CreateInventoryForm
    if request.method == "POST":
        form = CreateInventoryForm(request.POST)
        if form.is_valid():
            invenvt = form.save(commit=False)
            invenvt.branch = request.user.branch
            invenvt.save()
            messages.success(request, 'successfully created')
            return redirect('inventorys')
            # find out why it is redirecting to a wrong url after creating an inventory
    
    if product_contains_query != '' and product_contains_query is not None:
        inventory_page = inventory.filter(product__product_name__icontains=product_contains_query)

    context = {
        'branch':branch,
        'inventory':inventory,
        'product':product,
        'form':form,
        'inventory_page':inventory_page,
        'nums':nums,
    }
    return render(request, 'ims/inventory.html', context)

# @for_admin
# @login_required
# @is_unsubscribed
# def inventory(request, pk):
#     inventory = Inventory.objects.get(id=pk)

#     context = {
#         'inventory':inventory
#     }
#     return render(request, 'ims/edit_inventory.html', context)


@for_admin
def edit_inventory(request, pk):
    branch = Branch.objects.get(id=pk)
    if request.method == 'POST':
        inventory = Inventory.objects.filter().get(id = request.POST.get('id'))
        if inventory != None:
            form = ReorderForm(request.POST, instance=inventory)
            if form.is_valid():
                form.save()
                messages.success(request, 'successfully updated')
                return redirect('inventorys/'+str(branch.id))


def adminRestock(request):
    if request.method == 'POST':
        inventory = Inventory.objects.get(id = request.POST.get('id'))
        if inventory != None:
            form  = AdminRestockForm(request.POST, instance=inventory)
            if form.is_valid():
                form.save(commit=False)
                inventory.quantity += inventory.quantity_restocked
                inventory.save()
                messages.success(request, 'successfully updated')
                return redirect('branchinv')


@for_sub_admin
def restock(request):
    branch = request.user.branch
    if request.method == 'POST':
        inventory = Inventory.objects.filter(branch_id = branch).get(id = request.POST.get('id'))
        if inventory != None:
            form = RestockForm(request.POST, instance=inventory)
            if form.is_valid():
                invent = form.save(commit=False)
                invent.quantity += invent.quantity_restocked
                invent.branch = request.user.branch
                invent.save()
            
                messages.success(request, 'successfully updated')
                return redirect('inventorys')

    context = {
        'branch':branch
    }
    return HttpResponse(context)

@for_sub_admin
@login_required
# @is_unsubscribed
def inventoryView(request, pk):
    branch = Branch.objects.get(id=pk)
    inventory = Inventory.objects.filter(branch_id = pk).all()
    product = Product.objects.filter().all()
    paginator = Paginator(Inventory.objects.filter(branch_id = pk).all(), 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" *inventory_page.paginator.num_pages
    product_contains_query = request.GET.get('product')

    if product_contains_query != '' and product_contains_query is not None:
        inventory_page = inventory.filter(product__product_name__icontains=product_contains_query)

    context = {
        'branch':branch,
        'inventory':inventory,
        'product':product,
        'inventory_page':inventory_page,
        'nums':nums,
    }
    return render(request, 'ims/product_list.html', context)


@for_admin
@login_required
# @is_unsubscribed
def branchCount(request):
    branch = Branch.objects.all()

    context = {
        'branch':branch
    }

    return render(request, 'ims/branch_count.html', context)
    
def adminCountView(request, pk):
    branch = Branch.objects.get(id=pk)
    inventory = Inventory.objects.filter(branch_id = pk).all()
    audit = Inventory.history.filter(branch_id = pk).all()

    context = {
        'branch':branch,
        'inventory':inventory,
        'audit':audit
    }
    return render(request, 'ims/admin_count.html', context)


@for_sub_admin
@login_required
# @is_unsubscribed
def countView(request):
    branch = request.user.branch
    inventory = Inventory.objects.filter(branch_id = branch).all()
    audit = Inventory.history.filter(branch_id = branch).all()

    context = {
        'branch':branch,
        'inventory':inventory,
        'audit':audit
    }
    return render(request, 'ims/count.html', context)


@for_sub_admin
def addCount(request):
    if request.method == 'POST':
        branch = request.user.branch
        inventory = Inventory.objects.filter(branch_id = branch).get(id = request.POST.get('id'))
        if request.method != None:
            form = AddCountForm(request.POST, instance=inventory)
            if form.is_valid():
                invent = form.save(commit=False)
                invent.variance = inventory.count - inventory.store_quantity
                invent.branch = request.user.branch
                invent.save()
                messages.success(request, 'Count Added Successfully')
                return redirect('count')
    context = {
        'branch':branch
    }

    return HttpResponse(context)

@for_admin
def delete_inventory(request, pk):
    branch = Branch.objects.get(id=pk)
    if request.method == 'POST':
        inventory = Inventory.objects.filter(branch_id = pk).get(id = request.POST.get('id'))
        if inventory != None:
            inventory.delete()
            messages.success(request, "Succesfully deleted")
            return redirect('inventorys/'+str(branch.id))


@for_admin
@login_required
# @is_unsubscribed
def branchAudit(request):
    branch = Branch.objects.all()

    context = {
        'branch':branch
    }

    return render(request, 'ims/branch_audit.html', context)


@for_admin
@login_required
# @is_unsubscribed
def inventoryAudit(request, pk):
    branch = Branch.objects.get(id=pk)
    inventory = Inventory.objects.filter(branch_id = pk).all()
    audit = Inventory.history.filter(branch_id = pk).all()
    paginator = Paginator(Inventory.history.filter(branch_id = pk).all(), 15)
    page = request.GET.get('page')
    audit_page = paginator.get_page(page)
    nums = "a" *audit_page.paginator.num_pages
    product_contains_query = request.GET.get('product')

    if product_contains_query != '' and product_contains_query is not None:
        audit_page = inventory.filter(product__product_name__icontains=product_contains_query)
    context = {
        'branch': branch,
        'inventory':inventory,
        'audit':audit,
        'audit_page':audit_page,
        'nums':nums
    }
    return render(request, 'ims/price_audit.html', context)

@for_admin
def export_audit_csv(request, pk):
    branch = Branch.objects.get(id=pk)
    response = HttpResponse(content_type = 'text/csv')
    response['Content-Disposition']='attachment; filename = Audit History'+str(datetime.now())+'.csv'
    writer = csv.writer(response)
    writer.writerow(['Staff', 'Product', 'Date Restocked', 'Quantity Restocked', 'New Cost Price', 'New Sale Price'])
    
    audit = Inventory.history.filter(branch_id = pk).all()
    
    for audit in audit:
        writer.writerow([audit.history_user, audit.product.product_name, audit.history_date, audit.quantity_restocked, audit.cost_price, audit.sale_price])
    
    return response


@login_required
# @is_unsubscribed
@for_admin
def staffs(request): 
    staff = CustomUser.objects.all()
    paginator = Paginator(CustomUser.objects.all(), 15)
    page = request.GET.get('page')
    staff_page = paginator.get_page(page)
    nums = "a" *staff_page.paginator.num_pages
    staff_contains = request.GET.get('username')
    form = UserCreateForm()
    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, 'Account successfully created for ' + username)

    if staff_contains != '' and staff_contains is not None:
        staff_page = staff.filter(username__icontains=staff_contains)
   
    context = {
        'staff':staff,
        'staff_page':staff_page,
        'nums':nums,
        'form':form
    }
    return render(request, 'ims/staff.html', context)


@login_required
# @is_unsubscribed
@for_admin
def staff(request, pk):
    staff = CustomUser.objects.get(id=pk)
    form = UserEditForm()

    context = {
        'staff':staff,
        'form':form
    }
    return render(request, 'ims/staff_edit.html', context)


@login_required
# @is_unsubscribed
@for_admin
def edit_staff(request):
    if request.method == 'POST':
        staff = CustomUser.objects.get(id=request.POST.get('id'))
        if staff != None:
            form = UserForm(request.POST, instance=staff)
            if form.is_valid():
                form.save()
                messages.success(request, 'successfully updated')
                return redirect('staff')


@for_admin
def delete_staff(request):
    if request.method == 'POST':
        staff = CustomUser.objects.get(id = request.POST.get('id')) 
        if staff != None:
            staff.delete()
            messages.success(request, "Succesfully deleted")
            return redirect('staff')


@for_admin
@login_required
# @is_unsubscribed
def record(request):
    login_trail = LoggedIn.objects.all().order_by('-timestamp')
    paginator = Paginator(LoggedIn.objects.all(), 15)
    page = request.GET.get('page')
    login_trail_page = paginator.get_page(page)
    nums = "a" *login_trail_page.paginator.num_pages
    staff_contains = request.GET.get('staff')

    if staff_contains != '' and staff_contains is not None:
        login_trail_page = login_trail.filter(staff__icontains=staff_contains)

    context = {
        'login_trail':login_trail,
        'login_trail_page':login_trail_page,
        'nums':nums
    }
    return render(request, 'ims/records.html', context)

@login_required
# @is_unsubscribed
def errorTicket(request):
    ticket = ErrorTicket.objects.all()
    pending = ErrorTicket.objects.filter(status='Pending')

    context = {
        'ticket':ticket,
        'pending':pending
    }

    return render(request, 'ims/ticket.html', context)

@login_required
# @is_unsubscribed
def Ticket(request, pk):
    ticket = ErrorTicket.objects.get(id=pk)
    form = UpdateTicketForm(instance=ticket)
    if request.method == 'POST':
        form = UpdateTicketForm(request.POST, instance=ticket)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ticket viewed')
            return redirect('ticket')

    context = {
        'ticket':ticket
    }
    return render(request, 'ims/view_ticket.html', context)

@login_required
# @is_unsubscribed
def createTicket(request):
    staff = CustomUser.objects.all()
    form = CreateTicketForm()
    if request.method == 'POST':
        form = CreateTicketForm(request.POST or None)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.staff = request.user
            ticket.pos = ticket.staff.pos
            ticket.branch = ticket.staff.branch
            ticket.save()
            messages.success(request, 'Ticket Created Successfully')
            return redirect('create_ticket')

    context = {
        'staff':staff
    }
    
    return render(request, 'ims/create_ticket.html', context)
