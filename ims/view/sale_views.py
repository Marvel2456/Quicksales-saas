from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect
from django.contrib import messages
from datetime import datetime, date
from ims.models import Category, Product, Sale, SalesItem, Inventory, ErrorTicket
from account.models import CustomUser, Branch, ActivityLog
from django.contrib.auth.decorators import login_required
from ims.forms import *
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
import csv
import json
from account.decorators import role_required
from django.template.loader import get_template
from xhtml2pdf import pisa



# Write your views here.

@role_required(roles=['owner'])
@login_required(login_url=('login'))
# @is_unsubscribed
def branchStore(request):
    organization = request.user.organization
    inventory = Inventory.objects.filter(organization=organization).all().order_by('branch')
    paginator = Paginator(inventory, 15)
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


@role_required(roles=['owner', 'sales'])
@login_required
# @is_unsubscribed
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



@role_required(roles=['owner', 'sales'])
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


@role_required(roles=['owner', 'sales'])
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


@role_required(roles=['owner']) 
@login_required
# @is_unsubscribed
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


@role_required(roles=['owner'])
@login_required
def sale(request, pk):
    sale = Sale.objects.get(id=pk)

    context = {
        'sale':sale
    }
    return render(request, 'modals/sales_delete.html', context)

@role_required(roles=['owner'])
@login_required
def sale_delete(request):
    if request.method == 'POST':
        sale = Sale.objects.get(id = request.POST.get('id'))
        if sale != None:
            sale.delete()
            messages.success(request, "Succesfully deleted")
            return redirect('sales')

@role_required(roles=['owner'])
@login_required
def export_sales_csv(request):
    response = HttpResponse(content_type = 'text/csv')
    response['Content-Disposition']='attachment; filename = Sales History'+str(datetime.now())+'.csv'
    writer = csv.writer(response)
    writer.writerow(['Sales Rep', 'Trans Id', 'Date', 'Quantity', 'Total', 'Profit'])
    
    sale = Sale.objects.all()
    
    for sale in sale:
        writer.writerow([sale.staff, sale.transaction_id, sale.date_updated, sale.get_cart_items, sale.final_total_price, sale.total_profit])
    
    return response

@role_required(roles=['owner'])
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
    

@role_required(roles=['owner', 'sales'])
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

