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
@login_required
def branchStore(request):
    organization = request.user.organization
    branch_qs = Branch.objects.filter(organization=organization)

    paginator = Paginator(branch_qs, 15)
    page = request.GET.get('page')
    branch_page = paginator.get_page(page)
    nums = "a" * branch_page.paginator.num_pages

    branch_contains_query = request.GET.get('branch')
    if branch_contains_query:
        branch_page = branch_qs.filter(name__icontains=branch_contains_query)

    context = {
        'branch': branch_qs,
        'branch_page': branch_page,
        'nums': nums
    }
    return render(request, 'ims/branchstore.html', context)



@role_required(roles=['owner', 'sales'])
@login_required
# @is_unsubscribed
def store(request, pk):
    organization = request.user.organization
    branch = Branch.objects.get(organization=organization, id=pk)
    inventory = Inventory.objects.filter(branch=branch).all().order_by('-last_updated')
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
def cart(request, pk):
    organization = request.user.organization
    
    if request.user.is_authenticated:
        staff = request.user
        branch = Branch.objects.get(organization=organization, id=pk)
        inventory = Inventory.objects.filter(branch=branch)

        sale, _ = Sale.objects.get_or_create(
            staff=staff, branch=branch, organization=organization, completed=False
        )

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
def checkout(request, pk):
    organization = request.user.organization
       
    if request.user.is_authenticated:
        staff = request.user
        branch = Branch.objects.get(organization=organization, id=pk)
        inventory = Inventory.objects.filter(branch=branch)

        sale, _ = Sale.objects.get_or_create(
            staff=staff, branch=branch, organization=organization, completed=False
        )

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


def updateCart(request, pk):
    data = json.loads(request.body)
    inventoryId = data['inventoryId']
    action = data['action']
    print('inventory:', inventoryId)
    print('Action:', action)
   
    organization = request.user.organization
    staff = request.user
    branch = Branch.objects.get(organization=organization, id=pk)
    inventory = Inventory.objects.filter(branch_id = branch).get(id=inventoryId)
    sale, _ = Sale.objects.get_or_create(
        staff=staff, branch=branch, organization=organization, completed=False
    )


    saleItem, created = SalesItem.objects.get_or_create(
        sale=sale, branch=branch, inventory=inventory
    )

    if action == 'add':
        saleItem.quantity = (saleItem.quantity + 1)
    saleItem.save()

    if saleItem.quantity <= 0:
        saleItem.delete()

    context = {
        'branch': str(branch.id),
        'qty': sale.get_cart_items,
    }

    return JsonResponse(context, safe=False)



def updateQuantity(request, pk):
    data = json.loads(request.body)
    input_value = int(data['val'])
    inventory_Id = data['invent_id']
    
    organization = request.user.organization
    staff = request.user
    try:
        branch = Branch.objects.get(organization=organization, id=pk)
    except Branch.DoesNotExist:
        return JsonResponse({'error': 'Branch not found'}, status=404)

    try:
        inventory = Inventory.objects.get(branch=branch, id=inventory_Id)
    except Inventory.DoesNotExist:
        return JsonResponse({'error': 'Inventory not found'}, status=404)

    sale, _ = Sale.objects.get_or_create(staff=staff, organization=organization, branch=branch, completed=False)
    saleItem, _ = SalesItem.objects.get_or_create(sale=sale, branch=branch, inventory=inventory)

    saleItem.quantity = input_value
    saleItem.save()

    if saleItem.quantity <= 0:
        saleItem.delete()

    context = {
        'branch':str(branch.id),
        'sub_total':saleItem.get_total,
        'final_total':sale.get_cart_total,
        'total_quantity':sale.get_cart_items,
    }

    return JsonResponse(context, safe=False)



def sale_complete(request, pk):
    transaction_id = datetime.now().timestamp()
    data = json.loads(request.body)

    organization = request.user.organization
    staff = request.user

    try:
        branch = Branch.objects.get(organization=organization, id=pk)
    except Branch.DoesNotExist:
        return JsonResponse({'error': 'Branch not found'}, status=404)

    try:
        sale = Sale.objects.get(
            staff=staff, branch=branch, organization=organization, completed=False
        )
    except Sale.DoesNotExist:
        return JsonResponse({'error': 'No open sale found'}, status=404)

    sale.transaction_id = transaction_id
    total = float(data['payment']['total_cart'])
    sale.final_total_price = sale.get_cart_total
    sale.total_profit = sale.get_total_profit

    method = data['payment'].get('method')
    if method:
        sale.method = method

    if total == sale.get_cart_total:
        sale.completed = True

    sale.save()

    messages.success(request, 'sale completed')

    return JsonResponse({
        'branch': str(branch.id),
        'completed': sale.completed,
        'sale_id': str(sale.id),
        'transaction_id': sale.transaction_id,
        'final_total': sale.final_total_price,
        'method': sale.method,
    })


@role_required(roles=['owner'])
@login_required
def branchSales(request):
    organization = request.user.organization
    branch_qs = Branch.objects.filter(organization=organization)

    paginator = Paginator(branch_qs, 15)
    page = request.GET.get('page')
    branch_page = paginator.get_page(page)
    nums = "a" * branch_page.paginator.num_pages

    branch_contains_query = request.GET.get('branch')
    if branch_contains_query:
        branch_page = branch_qs.filter(name__icontains=branch_contains_query)

    context = {
        'branch': branch_qs,
        'branch_page': branch_page,
        'nums': nums
    }
    return render(request, 'ims/branchsales.html', context)


@role_required(roles=['owner']) 
@login_required
# @is_unsubscribed
def sales(request, pk):
    organization = request.user.organization
    branch = Branch.objects.get(organization=organization, id=pk)
    sale = Sale.objects.filter(branch=branch).order_by('-date_updated')
    paginator = Paginator(Sale.objects.filter(branch=branch).order_by('-date_updated'), 10)
    page = request.GET.get('page')
    sale_page = paginator.get_page(page)
    nums = "a" *sale_page.paginator.num_pages
    start_date_contains = request.GET.get('start_date')
    end_date_contains = request.GET.get('end_date')
    rep_contains_query = request.GET.get('rep')

    if start_date_contains != '' and start_date_contains is not None:
        sale_page = sale.filter(date_updated__gte=start_date_contains)

    if end_date_contains != '' and end_date_contains is not None:
        sale_page = sale.filter(date_updated__lt=end_date_contains)

    if rep_contains_query != '' and rep_contains_query is not None:
        sale_page = sale.filter(staff__first_name__icontains=rep_contains_query)

    context = {
        'branch':branch,
        'sale':sale,
        'sale_page':sale_page,
        'nums':nums
    }
    return render(request, 'ims/sales.html', context)


def sale_pdf(request, pk):
    organization = request.user.organization
    branch = Branch.objects.get(organization=organization, id=pk)
    sale = Sale.objects.filter(branch=branch)

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
def export_sales_csv(request, pk):
    organization = request.user.organization
    branch = Branch.objects.get(organization=organization, id=pk)
    response = HttpResponse(content_type = 'text/csv')
    response['Content-Disposition']='attachment; filename = Sales History'+str(datetime.now())+'.csv'
    writer = csv.writer(response)
    writer.writerow(['Sales Rep', 'Trans Id', 'Date', 'Quantity', 'Total', 'Profit'])
    
    sale = Sale.objects.filter(branch=branch)
    
    for sale in sale:
        writer.writerow([sale.staff, sale.transaction_id, sale.date_updated, sale.get_cart_items, sale.final_total_price, sale.total_profit])
    
    return response

@role_required(roles=['owner'])
def export_profit_csv(request, pk):
    organization = request.user.organization
    branch = Branch.objects.get(organization=organization, id=pk)
    start_date_contains = request.GET.get('start_date')
    end_date_contains = request.GET.get('end_date')

    response = HttpResponse(content_type = 'text/csv')
    response['Content-Disposition']='attachment; filename = Profit History'+str(datetime.now())+'.csv'
    writer = csv.writer(response)
    writer.writerow(['Sales Rep', 'Trans Id', 'Date', 'Quantity', 'Total', 'Profit'])
    
    
    sale = Sale.objects.filter(branch = branch)

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
def reciept(request, pk):
    organization = request.user.organization
    try:
        sale = Sale.objects.get(id=pk, branch__organization=organization)
    except Sale.DoesNotExist:
        return redirect('store')  

    salesitem = sale.salesitem_set.all()
    
    context = {
        'salesitem': salesitem,
        'sale': sale,
        'branch': sale.branch,
    }
    return render(request, 'ims/reciept.html', context)


def profitData(request, pk):
    profits = []

    sale = Sale.objects.get(id = pk)
    items = sale.salesitem_set.all()

    for i in items:
        profits.append({i.get_profit:i.inventory.product.product_name})

    return JsonResponse(profits, safe=False)

