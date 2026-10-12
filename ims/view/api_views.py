from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.db import transaction
from ims.models import Category, Product, Sale, SalesItem, Inventory, ErrorTicket, OfflineSaleTemp
from account.models import Branch, Notification
from account.decorators import role_required
from account.utils import get_request_organization
from datetime import datetime
import json
import uuid


# Prefix used in OfflineSaleTemp.temp_id to map offline-created carts to server Sales
# (distinct from checkout temp IDs, which start with 'offline_').
CART_MAPPING_PREFIX = 'cart:'


def _is_valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _normalize_cart_items(items):
    """Merge duplicate inventory lines and drop invalid/non-positive rows."""
    requested = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        inv_id = str(item.get('inventory_id') or '')
        try:
            qty = int(item.get('quantity', 0))
        except (TypeError, ValueError):
            qty = 0
        if qty > 0 and _is_valid_uuid(inv_id):
            requested[inv_id] = requested.get(inv_id, 0) + qty
    return requested


def _serialize_open_sale(sale):
    items = [
        {'inventory_id': str(si.inventory_id), 'quantity': si.quantity}
        for si in sale.salesitem_set.all()
        if si.inventory_id and (si.quantity or 0) > 0
    ]
    return {
        'id': str(sale.id),
        'date_added': sale.date_added.isoformat() if sale.date_added else None,
        'items': items,
    }


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
    # When the offline cart was a continuation of an online cart, this is the
    # UUID of that open Sale. We complete it instead of creating a new Sale.
    server_sale_id = data.get('server_sale_id')
    
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
            
            # Step 0: Resolve the original online Sale (if this cart continued one)
            target_sale = None
            if server_sale_id and _is_valid_uuid(server_sale_id):
                target_sale = Sale.objects.select_for_update().filter(
                    id=server_sale_id,
                    branch=branch,
                    organization=organization,
                    staff=request.user,
                ).first()
                
                # Conflict policy: if the same cart was already completed/cancelled
                # elsewhere (e.g. another device), reject to prevent a double sale.
                if target_sale is not None and (target_sale.completed or target_sale.cancelled):
                    state = 'cancelled' if target_sale.cancelled else 'completed'
                    item_lines = ', '.join(
                        f"{i.get('inventory_id')} x{i.get('quantity')}" for i in items if isinstance(i, dict)
                    )
                    ErrorTicket.objects.create(
                        organization=organization,
                        branch=branch,
                        staff=request.user,
                        title="Offline Sync Conflict: Sale already closed",
                        description=(
                            f"An offline checkout (Temp ID: {temp_id}, method: {method}) was made for sale "
                            f"{target_sale.id}, but that sale had already been {state} on the server. "
                            f"The offline checkout was rejected to prevent a duplicate sale. "
                            f"Items: {item_lines}"
                        ),
                        status="Pending"
                    )
                    return JsonResponse({
                        'error': f"This cart was already {state} on another device. Offline checkout rejected; an error ticket was logged."
                    }, status=409)
            
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
                
            # Step 2: Complete the original online Sale, or create a new one
            if target_sale is not None:
                sale = target_sale
                sale.total_profit = recalculated_profit
                sale.final_total_price = recalculated_total
                sale.transaction_id = temp_id
                sale.method = method
                sale.completed = True
                sale.save()
                
                # Replace the open cart lines with exactly what was paid for offline
                existing_items = {}
                for si in sale.salesitem_set.all():
                    key = str(si.inventory_id)
                    if si.inventory_id is None or key in existing_items:
                        si.delete()
                    else:
                        existing_items[key] = si
                paid_ids = {str(v['inventory'].id) for v in validated_items}
                for key, si in existing_items.items():
                    if key not in paid_ids:
                        si.delete()
            else:
                existing_items = {}
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
            
            # Step 3: Create/update SalesItems and decrement Inventory counts
            for v_item in validated_items:
                inv = v_item['inventory']
                qty = v_item['quantity']
                
                sale_item = existing_items.get(str(inv.id))
                if sale_item is not None:
                    sale_item.total = v_item['total']
                    sale_item.cost_total = v_item['cost_total']
                    sale_item.quantity = qty
                    sale_item.save()
                else:
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
        
        # The completed cart is no longer the active online sale
        session_key = f'active_sale_{branch.id}'
        if request.session.get(session_key) == str(sale.id):
            request.session.pop(session_key, None)
                    
        return JsonResponse({
            'success': True,
            'sale_id': str(sale.id),
            'transaction_id': sale.transaction_id,
            'continued_online_sale': target_sale is not None
        }, status=201)
        
    except Exception as e:
        return JsonResponse({'error': f"Sync process failed: {str(e)}"}, status=500)


@role_required(roles=['owner', 'sales'])
@login_required
@require_GET
def get_open_sales(request, pk):
    """Return the current user's open (un-checked-out) sales for this branch so the
    browser can mirror them into IndexedDB and continue them if the network drops."""
    organization = get_request_organization(request)
    branch = get_object_or_404(Branch, id=pk, organization=organization)
    
    open_sales = Sale.objects.filter(
        staff=request.user,
        branch=branch,
        organization=organization,
        completed=False,
        cancelled=False,
    ).prefetch_related('salesitem_set').order_by('date_added')
    
    sales_data = [_serialize_open_sale(s) for s in open_sales]
    sale_ids = {s['id'] for s in sales_data}
    
    # Same fallback as the cart view: most recent open sale if the session has none
    active_sale_id = request.session.get(f'active_sale_{branch.id}')
    if active_sale_id not in sale_ids:
        active_sale_id = sales_data[-1]['id'] if sales_data else None
    
    return JsonResponse({
        'sales': sales_data,
        'active_sale_id': active_sale_id,
    })


@role_required(roles=['owner', 'sales'])
@login_required
@require_POST
def sync_cart(request, pk):
    """Reconcile one un-checked-out cart that was edited (or created/cancelled) offline.
    
    Payload: {local_id, server_sale_id?, items: [{inventory_id, quantity}], cancelled, make_active}
    - Server-backed carts: the open Sale's lines are replaced with `items`.
    - Offline-only carts: a new open Sale is created (idempotent via OfflineSaleTemp).
    - Quantities are capped to available stock; adjustments are reported back.
    """
    organization = get_request_organization(request)
    branch = get_object_or_404(Branch, id=pk, organization=organization)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
    
    local_id = str(data.get('local_id') or '')[:90]
    server_sale_id = data.get('server_sale_id')
    if server_sale_id and not _is_valid_uuid(server_sale_id):
        return JsonResponse({'error': 'Invalid server_sale_id'}, status=400)
    requested = _normalize_cart_items(data.get('items'))
    cancelled = bool(data.get('cancelled'))
    make_active = bool(data.get('make_active'))
    session_key = f'active_sale_{branch.id}'
    mapping_key = f"{CART_MAPPING_PREFIX}{local_id}" if local_id else None
    
    try:
        with transaction.atomic():
            sale = None
            conflict = False
            
            if server_sale_id:
                sale = Sale.objects.select_for_update().filter(
                    id=server_sale_id,
                    staff=request.user,
                    branch=branch,
                    organization=organization,
                ).first()
                if sale is not None and (sale.completed or sale.cancelled):
                    # Closed elsewhere while we were offline; keep the cashier's items
                    # in a fresh open sale instead of resurrecting the closed one.
                    conflict = True
                    sale = None
            elif mapping_key:
                mapping = OfflineSaleTemp.objects.filter(temp_id=mapping_key).first()
                if mapping and mapping.sale_id:
                    sale = Sale.objects.select_for_update().filter(
                        id=mapping.sale_id,
                        staff=request.user,
                        branch=branch,
                        organization=organization,
                        completed=False,
                        cancelled=False,
                    ).first()
            
            # Cancelled offline: mirror cancel_sale semantics
            if cancelled:
                if sale is not None:
                    sale.cancelled = True
                    sale.completed = True
                    sale.final_total_price = 0
                    sale.total_profit = 0
                    sale.transaction_id = sale.transaction_id or f"CANCEL-{int(datetime.now().timestamp())}"
                    sale.save(update_fields=['cancelled', 'completed', 'final_total_price', 'total_profit', 'transaction_id'])
                    if request.session.get(session_key) == str(sale.id):
                        request.session.pop(session_key, None)
                return JsonResponse({
                    'success': True,
                    'cancelled': True,
                    'server_sale_id': str(sale.id) if sale else None,
                })
            
            if sale is None:
                if not requested:
                    # Nothing worth keeping (empty cart)
                    return JsonResponse({
                        'success': True,
                        'server_sale_id': None,
                        'conflict': conflict,
                        'adjustments': [],
                    })
                sale = Sale.objects.create(staff=request.user, branch=branch, organization=organization)
                if mapping_key and not server_sale_id:
                    OfflineSaleTemp.objects.update_or_create(temp_id=mapping_key, defaults={'sale': sale})
            
            # Lock the inventory rows we are about to reserve
            inventories = {
                str(inv.id): inv
                for inv in Inventory.objects.select_for_update().select_related('product').filter(
                    id__in=list(requested.keys()),
                    branch=branch,
                    organization=organization,
                )
            }
            
            existing_items = {}
            for si in sale.salesitem_set.all():
                key = str(si.inventory_id)
                if si.inventory_id is None or key in existing_items or key not in requested:
                    si.delete()
                else:
                    existing_items[key] = si
            
            adjustments = []
            for inv_id, qty in requested.items():
                inv = inventories.get(inv_id)
                sale_item = existing_items.get(inv_id)
                if inv is None:
                    if sale_item is not None:
                        sale_item.delete()
                    adjustments.append({
                        'inventory_id': inv_id, 'product_name': None,
                        'requested': qty, 'applied': 0, 'reason': 'not_found',
                    })
                    continue
                
                # store_quantity already subtracts every open sale's lines (including
                # this one), so add back what this cart currently holds.
                own_reserved = sale_item.quantity if sale_item is not None else 0
                available = max(0, inv.store_quantity + (own_reserved or 0))
                applied = min(qty, available)
                
                if applied < qty:
                    adjustments.append({
                        'inventory_id': inv_id,
                        'product_name': inv.product.product_name,
                        'requested': qty,
                        'applied': applied,
                        'reason': 'insufficient_stock',
                    })
                
                if applied <= 0:
                    if sale_item is not None:
                        sale_item.delete()
                    continue
                
                if sale_item is None:
                    sale_item = SalesItem(
                        sale=sale, branch=branch, organization=organization, inventory=inv,
                    )
                sale_item.quantity = applied
                sale_item.save()
            
            if make_active:
                request.session[session_key] = str(sale.id)
                request.session.modified = True
        
        return JsonResponse({
            'success': True,
            'server_sale_id': str(sale.id),
            'conflict': conflict,
            'adjustments': adjustments,
            'sale': _serialize_open_sale(sale),
        })
    except Exception as e:
        return JsonResponse({'error': f"Cart sync failed: {str(e)}"}, status=500)
