from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from ims.models import Category, Product, Sale, SalesItem, Inventory, ErrorTicket, OfflineSaleTemp
from account.models import Branch, Notification
from account.decorators import role_required
from account.utils import get_request_organization
import json

@role_required(roles=['owner', 'sales'])
@login_required
def get_offline_data(request, pk):
    """API endpoint to fetch all active product inventory for offline catalog caching"""
    organization = get_request_organization(request)
    branch = get_object_or_404(Branch, id=pk, organization=organization)
    
    # Fetch categories
    categories = Category.objects.filter(branch=branch, organization=organization)
    categories_data = [{'id': str(cat.id), 'name': cat.category_name} for cat in categories]
    
    # Fetch active inventory
    inventory_qs = Inventory.objects.filter(
        branch=branch,
        organization=organization
    ).select_related('product', 'product__category')
    
    products_data = []
    for item in inventory_qs:
        products_data.append({
            'id': str(item.id),
            'product_id': str(item.product.id),
            'product_name': item.product.product_name,
            'category_id': str(item.product.category.id) if item.product.category else None,
            'category_name': item.product.category.category_name if item.product.category else 'Uncategorized',
            'sale_price': item.sale_price or 0.0,
            'cost_price': item.cost_price or 0.0,
            'reorder_level': item.reorder_level or 0,
            'store_quantity': item.store_quantity,
            'product_code': item.product.product_code or ''
        })
        
    return JsonResponse({
        'categories': categories_data,
        'products': products_data,
        'branch_name': branch.name,
        'organization_name': organization.name,
        'organization_logo': organization.logo.url if organization.logo else None
    }, safe=False)


@csrf_exempt
@role_required(roles=['owner', 'sales'])
@login_required
def sync_sale(request, pk):
    """API endpoint to sync offline sales to the cloud with concurrency locks and idempotency checks"""
    organization = get_request_organization(request)
    branch = get_object_or_404(Branch, id=pk, organization=organization)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
        
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
        
    temp_id = data.get('tempId')
    items = data.get('items', [])
    method = data.get('method', 'Cash')
    
    if not temp_id:
        return JsonResponse({'error': 'tempId is required'}, status=400)
    if not items:
        return JsonResponse({'error': 'Cart items are required'}, status=400)
        
    # Idempotency Check: if this tempId has already been successfully synced, return the existing sale
    existing_sync = OfflineSaleTemp.objects.filter(temp_id=temp_id).select_related('sale').first()
    if existing_sync:
        return JsonResponse({
            'success': True,
            'sale_id': str(existing_sync.sale.id),
            'transaction_id': existing_sync.sale.transaction_id,
            'message': 'Already synced (idempotent)'
        }, status=200)
        
    try:
        # Secure concurrency updates with database transaction
        with transaction.atomic():
            recalculated_total = 0.0
            recalculated_profit = 0.0
            
            # Step 1: Pre-validate stock availability and recalculate prices
            validated_items = []
            for item in items:
                invent_id = item.get('inventory_id')
                requested_qty = int(item.get('quantity', 0))
                
                if requested_qty <= 0:
                    continue
                    
                # Acquire database row lock on Inventory
                try:
                    inventory = Inventory.objects.select_for_update().get(
                        id=invent_id,
                        branch=branch,
                        organization=organization
                    )
                except Inventory.DoesNotExist:
                    return JsonResponse({
                        'error': f"Product/Inventory ID {invent_id} not found in this branch."
                    }, status=409)
                    
                # Stock limit verification
                if inventory.quantity < requested_qty:
                    # Log an automatic Error Ticket for inventory management visibility
                    ErrorTicket.objects.create(
                        organization=organization,
                        branch=branch,
                        staff=request.user,
                        title=f"Offline Sync Shortage: {inventory.product.product_name}",
                        description=(
                            f"An offline checkout session (Temp ID: {temp_id}) requested {requested_qty} units of "
                            f"'{inventory.product.product_name}', but only {inventory.quantity} units were available in stock. "
                            "Sync aborted to prevent negative stock values."
                        ),
                        status="Pending"
                    )
                    return JsonResponse({
                        'error': f"Insufficient stock for '{inventory.product.product_name}'. Available: {inventory.quantity}, requested: {requested_qty}."
                    }, status=409)
                    
                item_total = (inventory.sale_price or 0.0) * requested_qty
                item_cost = (inventory.cost_price or 0.0) * requested_qty
                
                recalculated_total += item_total
                recalculated_profit += (item_total - item_cost)
                
                validated_items.append({
                    'inventory': inventory,
                    'quantity': requested_qty,
                    'total': item_total,
                    'cost_total': item_cost
                })
                
            if not validated_items:
                return JsonResponse({'error': 'No valid items found in sync payload'}, status=400)
                
            # Step 2: Create Sale instance
            sale = Sale.objects.create(
                organization=organization,
                branch=branch,
                staff=request.user,
                total_profit=recalculated_profit,
                final_total_price=recalculated_total,
                transaction_id=temp_id,
                method=method,
                completed=True
            )
            
            # Step 3: Create SalesItems and decrement Inventory counts
            for v_item in validated_items:
                inv = v_item['inventory']
                qty = v_item['quantity']
                
                SalesItem.objects.create(
                    organization=organization,
                    branch=branch,
                    inventory=inv,
                    sale=sale,
                    total=v_item['total'],
                    cost_total=v_item['cost_total'],
                    quantity=qty
                )
                
                # Update inventory quantity
                inv.quantity -= qty
                inv.quantity_restocked = 0
                inv.count = None
                inv.variance = 0
                inv.save()
                
            # Step 4: Record mapped Temp ID for idempotency register
            OfflineSaleTemp.objects.create(temp_id=temp_id, sale=sale)
            
            # High-value notification trigger
            if recalculated_total >= 50000:
                owner = organization.owned_by
                if owner and owner != request.user:
                    Notification.objects.create(
                        user=owner,
                        message=f"High-value offline sale synced: ₦{recalculated_total:,.2f} by {request.user.get_full_name() or request.user.email} at {branch.name} branch",
                        notification_type='success',
                        organization=organization,
                        is_read=False
                    )
                    
        return JsonResponse({
            'success': True,
            'sale_id': str(sale.id),
            'transaction_id': sale.transaction_id
        }, status=201)
        
    except Exception as e:
        return JsonResponse({'error': f"Sync process failed: {str(e)}"}, status=500)
