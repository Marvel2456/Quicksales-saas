from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect
from django.contrib import messages
from datetime import datetime, date
from ims.models import Category, Product, Sale, SalesItem, Inventory, ErrorTicket
from account.models import CustomUser, Branch, ActivityLog, Notification
from django.contrib.auth.decorators import login_required
from ims.forms import *
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
import csv
import json
from account.decorators import role_required
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.db.models import Sum



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

        sale = None
        items = []

        # Get active sale ID from session without creating a new one
        active_sale_id = request.session.get(f'active_sale_{branch.id}')
        if active_sale_id:
            try:
                sale = Sale.objects.get(
                    id=active_sale_id,
                    staff=staff,
                    branch=branch,
                    completed=False,
                    cancelled=False,
                )
                items = sale.salesitem_set.all()
            except Sale.DoesNotExist:
                request.session.pop(f'active_sale_{branch.id}', None)
                sale = None

        # Get all open sales for this staff/branch (exclude cancelled)
        open_sales = Sale.objects.filter(
            staff=staff,
            branch=branch,
            organization=organization,
            completed=False,
            cancelled=False,
        ).order_by('-date_added')

        # If no active sale in session but there are open sales, restore the most recent one
        # (user logged back in after session expired)
        if sale is None and open_sales.exists():
            sale = open_sales.first()
            request.session[f'active_sale_{branch.id}'] = str(sale.id)
            items = sale.salesitem_set.all()
        
    context = {
        'branch':branch,
        'items':items,
        'sale':sale,
        'inventory':inventory,
        'open_sales': open_sales,
        'active_sale_id': str(sale.id) if sale else '',
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

        # Get active sale from session
        active_sale_id = request.session.get(f'active_sale_{branch.id}')
        if active_sale_id:
            try:
                sale = Sale.objects.get(
                    id=active_sale_id,
                    staff=staff,
                    branch=branch,
                    completed=False,
                    cancelled=False,
                )
            except Sale.DoesNotExist:
                request.session.pop(f'active_sale_{branch.id}', None)
                messages.error(request, 'Active sale not found, please start a new sale')
                return redirect('store', pk=branch.id)
        else:
            messages.error(request, 'No active sale. Add an item from the store to start a sale.')
            return redirect('store', pk=branch.id)

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
    
    # Check if product is in stock
    if inventory.quantity <= 0:
        return JsonResponse({'error': 'Product is out of stock'}, status=400)
    
    # Get active sale from session
    active_sale_id = request.session.get(f'active_sale_{branch.id}')
    sale = None
    if active_sale_id:
        try:
            sale = Sale.objects.get(
                id=active_sale_id,
                staff=staff,
                branch=branch,
                completed=False,
                cancelled=False,
            )
        except Sale.DoesNotExist:
            sale = None

    # Reuse last open sale if session missing
    if sale is None:
        sale = Sale.objects.filter(
            staff=staff,
            branch=branch,
            organization=organization,
            completed=False,
            cancelled=False,
        ).order_by('-date_added').first()

    # Create sale only when first item is added and none exist
    if sale is None:
        sale = Sale.objects.create(staff=staff, branch=branch, organization=organization)
        request.session[f'active_sale_{branch.id}'] = str(sale.id)

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

    # Get active sale from session
    active_sale_id = request.session.get(f'active_sale_{branch.id}')
    if not active_sale_id:
        return JsonResponse({'error': 'No active sale'}, status=400)

    try:
        sale = Sale.objects.get(
            id=active_sale_id,
            staff=staff,
            branch=branch,
            completed=False,
            cancelled=False,
        )
    except Sale.DoesNotExist:
        return JsonResponse({'error': 'Active sale not found'}, status=404)
    
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

    # Get active sale from session
    active_sale_id = request.session.get(f'active_sale_{branch.id}')
    if not active_sale_id:
        return JsonResponse({'error': 'No active sale session'}, status=404)
    
    try:
        sale = Sale.objects.get(
            id=active_sale_id,
            staff=staff,
            branch=branch,
            organization=organization,
            completed=False,
            cancelled=False,
        )
    except Sale.DoesNotExist:
        # Sale might already be completed, check for it
        try:
            existing_sale = Sale.objects.get(
                id=active_sale_id,
                staff=staff,
                branch=branch,
                organization=organization,
            )
            if existing_sale.completed:
                return JsonResponse({'error': 'Sale already completed'}, status=400)
            else:
                return JsonResponse({'error': 'No open sale found'}, status=404)
        except Sale.DoesNotExist:
            return JsonResponse({'error': 'No open sale found'}, status=404)

    if sale.cancelled:
        return JsonResponse({'error': 'Sale already cancelled'}, status=400)

    sale.transaction_id = transaction_id
    total = float(data['payment']['total_cart'])
    sale.final_total_price = sale.get_cart_total
    sale.total_profit = sale.get_total_profit

    method = data['payment'].get('method')
    if method:
        sale.method = method

    if total == sale.get_cart_total:
        # Check if inventory has already been reduced for this completed sale
        if sale.completed:
            return JsonResponse({'error': 'Sale already completed and inventory adjusted'}, status=400)
            
        sale.completed = True
        
        # Reduce inventory for all items in this sale ONLY ONCE
        # Convert to list to avoid lazy evaluation issues with queryset
        sale_items = list(sale.salesitem_set.all())
        
        for sale_item in sale_items:
            if sale_item.inventory:
                # IMPORTANT: Refresh inventory from DB to get latest state
                inventory_item = sale_item.inventory
                inventory_item.refresh_from_db()
                
                # Reduce quantity by the amount sold
                inventory_item.quantity -= sale_item.quantity
                inventory_item.quantity_restocked = 0  # Prevent restock marker from leaking into history
                inventory_item.count = None  # Reset to null
                inventory_item.variance = 0  # Reset variance
                inventory_item.save()
        
        # NOTE: Keep SalesItems for sale history. They won't be counted in store_quantity
        # because store_quantity now only counts items from open (incomplete) sales.
        # This prevents double-tracking while preserving sales history.
        
        # Notify owner of high-value sales (e.g., sales over 50000)
        if sale.final_total_price and sale.final_total_price >= 50000:
            owner = organization.owned_by
            if owner and owner != staff:
                Notification.objects.create(
                    user=owner,
                    message=f"High-value sale completed: ₦{sale.final_total_price:,.2f} by {staff.get_full_name() or staff.email} at {branch.name} branch",
                    notification_type='success',
                    is_read=False
                )

    sale.save()
    
    # Clear active sale from session if it was completed
    if sale.completed:
        request.session.pop(f'active_sale_{branch.id}', None)

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
    sale_qs = Sale.objects.filter(branch=branch).order_by('-date_updated')
    
    # Get filter parameters
    start_date_contains = request.GET.get('start_date')
    end_date_contains = request.GET.get('end_date')
    rep_contains_query = request.GET.get('rep')

    # Apply filters to queryset before pagination
    if start_date_contains and start_date_contains != '':
        sale_qs = sale_qs.filter(date_updated__date__gte=start_date_contains)

    if end_date_contains and end_date_contains != '':
        sale_qs = sale_qs.filter(date_updated__date__lte=end_date_contains)

    if rep_contains_query and rep_contains_query != '':
        sale_qs = sale_qs.filter(staff__first_name__icontains=rep_contains_query)

    # Now paginate the filtered queryset
    paginator = Paginator(sale_qs, 10)
    page = request.GET.get('page')
    sale_page = paginator.get_page(page)
    nums = "a" * sale_page.paginator.num_pages

    context = {
        'branch':branch,
        'sale':sale_qs,
        'sale_page':sale_page,
        'nums':nums,
        'start_date': start_date_contains,
        'end_date': end_date_contains,
        'rep': rep_contains_query,
    }
    return render(request, 'ims/sales.html', context)


def sale_pdf(request, pk):
    organization = request.user.organization
    branch = Branch.objects.get(organization=organization, id=pk)
    sale_qs = Sale.objects.filter(branch=branch).order_by('-date_updated')

    # Apply same filters as sales list view
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    rep = request.GET.get('rep')

    if start_date and start_date != '':
        sale_qs = sale_qs.filter(date_updated__date__gte=start_date)
    if end_date and end_date != '':
        sale_qs = sale_qs.filter(date_updated__date__lte=end_date)
    if rep and rep != '':
        sale_qs = sale_qs.filter(staff__first_name__icontains=rep)

    # Aggregate totals
    agg = sale_qs.aggregate(
        total_sales=Sum('final_total_price'),
        total_profit=Sum('total_profit'),
    )
    total_sales = agg.get('total_sales') or 0
    total_profit = agg.get('total_profit') or 0
    total_quantity = sum(s.get_cart_items for s in sale_qs)

    template_path = 'ims/salepdf.html'
    context = {
        'sale': sale_qs,
        'branch': branch,
        'filters': {
            'start_date': start_date,
            'end_date': end_date,
            'rep': rep,
        },
        'summary': {
            'total_sales': total_sales,
            'total_profit': total_profit,
            'total_quantity': total_quantity,
        }
    }
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
    
    sale_qs = Sale.objects.filter(branch=branch)
    
    # Apply filters from request
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    rep = request.GET.get('rep')
    
    if start_date and start_date != '':
        sale_qs = sale_qs.filter(date_updated__date__gte=start_date)
    
    if end_date and end_date != '':
        sale_qs = sale_qs.filter(date_updated__date__lte=end_date)
    
    if rep and rep != '':
        sale_qs = sale_qs.filter(staff__first_name__icontains=rep)
    
    for sale in sale_qs:
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
        sale = sale.filter(date_updated__date__gte=start_date_contains)

    if end_date_contains:
        sale = sale.filter(date_updated__date__lte=end_date_contains)

    total_profits = sum(sale.values_list('total_profit', flat=True))
    for sale in sale:
        writer.writerow([sale.staff, sale.transaction_id, sale.date_updated, sale.get_cart_items, sale.final_total_price, sale.total_profit])
        
    writer.writerow(['Total Profit'])
    if total_profits:
        writer.writerow([total_profits])
    
    
    return response


# Multiple concurrent sales management endpoints

@role_required(roles=['owner', 'sales'])
@login_required
def create_new_sale(request, pk):
    """Create a new sale and set it as active"""
    organization = request.user.organization
    staff = request.user
    
    try:
        branch = Branch.objects.get(organization=organization, id=pk)
    except Branch.DoesNotExist:
        messages.error(request, 'Branch not found')
        return redirect('store', pk=pk)
    
    # Create new sale immediately
    sale = Sale.objects.create(staff=staff, branch=branch, organization=organization)
    
    # Set as active sale in session
    request.session[f'active_sale_{branch.id}'] = str(sale.id)
    
    messages.success(request, 'New sale created. Add items from the store.')
    return redirect('store', pk=branch.id)


@role_required(roles=['owner', 'sales'])
@login_required
def switch_sale(request, pk, sale_id):
    """Switch to a different open sale"""
    organization = request.user.organization
    staff = request.user
    
    try:
        branch = Branch.objects.get(organization=organization, id=pk)
        sale = Sale.objects.get(
            id=sale_id, staff=staff, branch=branch, 
            organization=organization, completed=False
        )
    except (Branch.DoesNotExist, Sale.DoesNotExist):
        messages.error(request, 'Sale not found')
        return redirect('cart', pk=pk)
    
    # Set as active sale in session
    request.session[f'active_sale_{branch.id}'] = str(sale.id)
    
    messages.success(request, f'Switched to sale (ID: {sale.id.hex[:8]})')
    return redirect('cart', pk=branch.id)


@role_required(roles=['owner', 'sales'])
@login_required
def cancel_sale(request, pk, sale_id):
    """Cancel a sale but keep history for reporting"""
    organization = request.user.organization
    staff = request.user
    
    try:
        branch = Branch.objects.get(organization=organization, id=pk)
        sale = Sale.objects.get(
            id=sale_id, staff=staff, branch=branch,
            organization=organization, completed=False
        )
    except (Branch.DoesNotExist, Sale.DoesNotExist):
        messages.error(request, 'Sale not found')
        return redirect('cart', pk=pk)
    
    # Restore inventory quantities ONLY if the sale was completed
    # (Open sales never reduced inventory - they only reserved items in store_quantity)
    sale_items = sale.salesitem_set.all()
    
    if sale.completed:
        # This should rarely happen as we look for completed=False above
        # But just in case, restore only if the sale was completed
        for sale_item in sale_items:
            if sale_item.inventory:
                inventory_item = sale_item.inventory
                # Restore the quantity by adding back what was in the sale
                inventory_item.quantity += sale_item.quantity
                inventory_item.save()
    
    # NOTE: Keep SalesItems for sale history. The cancelled flag on Sale prevents
    # them from being counted in store_quantity calculations.
    # For open sales being cancelled: the SalesItems disappearing from open_salesitems
    # query will automatically increase store_quantity (no manual restoration needed)
    
    # Mark sale as cancelled but keep record
    sale.cancelled = True
    sale.completed = True
    sale.final_total_price = 0
    sale.total_profit = 0
    sale.transaction_id = sale.transaction_id or f"CANCEL-{int(datetime.now().timestamp())}"
    sale.save(update_fields=['cancelled', 'completed', 'final_total_price', 'total_profit', 'transaction_id'])
    
    # Clear from session if it was the active sale
    active_sale_id = request.session.get(f'active_sale_{branch.id}')
    if active_sale_id == str(sale_id):
        request.session.pop(f'active_sale_{branch.id}', None)
    
    messages.success(request, 'Sale cancelled successfully')
    return redirect('cart', pk=branch.id)


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
        'organization': organization,
    }
    return render(request, 'ims/reciept.html', context)


def profitData(request, pk):
    profits = []

    sale = Sale.objects.get(id = pk)
    items = sale.salesitem_set.all()

    for i in items:
        profits.append({i.get_profit:i.inventory.product.product_name})

    return JsonResponse(profits, safe=False)

