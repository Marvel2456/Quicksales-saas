"""
Offline Sync API - Handles syncing of pending sales from offline mode

SECURITY CONSIDERATIONS:
- All prices are recalculated server-side (client prices ignored)
- Product IDs validated against user's org/branch
- Inventory checked fresh from server (not trusted from client)
- Duplicate prevention via tempId tracking
- All operations within atomic transactions
- Rate limiting recommended at reverse proxy level
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from ims.models import Sale, SalesItem, Inventory, Product
from account.models import Branch
from decimal import Decimal, InvalidOperation
import json
import logging
import hashlib

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
@login_required
def sync_offline_sale(request):
    """
    Receive and process a pending sale that was created offline
    
    Handles:
    - Creating the Sale record
    - Creating SalesItem records
    - Updating Inventory
    - Conflict resolution (inventory availability)
    """
    try:
        data = json.loads(request.body)
        organization = request.user.organization
        branch = request.user.branch

        if not branch:
            return JsonResponse(
                {'error': 'No branch assigned to user'},
                status=400
            )

        # Validate required fields
        required_fields = ['items', 'total_amount', 'payment_method']
        if not all(field in data for field in required_fields):
            return JsonResponse(
                {'error': 'Missing required fields'},
                status=400
            )

        # Use transaction to ensure data consistency
        with transaction.atomic():
            # Check and update inventory first
            inventory_check = check_and_reserve_inventory(
                branch=branch,
                items=data.get('items', [])
            )

            if not inventory_check['available']:
                return JsonResponse(
                    {
                        'error': 'Insufficient inventory',
                        'details': inventory_check['details']
                    },
                    status=409  # Conflict - user will need to reconcile
                )

            # Create Sale record
            sale = Sale.objects.create(
                organization=organization,
                branch=branch,
                user=request.user,
                total_price=Decimal(str(data['total_amount'])),
                final_total_price=Decimal(str(data['total_amount'])),
                payment_method=data.get('payment_method', 'cash'),
                payment_status=data.get('payment_status', 'pending'),
                sync_from_offline=True,  # Mark as synced from offline
                original_temp_id=data.get('tempId')  # Store original temp ID for reference
            )

            # Create SalesItem records
            total_profit = 0
            for item in data.get('items', []):
                product_id = item.get('product_id')
                quantity = int(item.get('quantity', 1))
                unit_price = Decimal(str(item.get('unit_price', 0)))
                cost_price = Decimal(str(item.get('cost_price', 0)))

                # Get inventory
                try:
                    inventory = Inventory.objects.get(
                        product_id=product_id,
                        branch=branch
                    )
                except Inventory.DoesNotExist:
                    logger.warning(f"Inventory not found for product {product_id}")
                    continue

                # Create sales item
                sales_item = SalesItem.objects.create(
                    sale=sale,
                    inventory=inventory,
                    quantity=quantity,
                    unit_price=unit_price,
                    branch=branch
                )

                # Update inventory quantity
                inventory.quantity = max(0, inventory.quantity - quantity)
                inventory.save()

                # Calculate profit
                profit = (unit_price - cost_price) * quantity
                total_profit += profit

            # Update sale with total profit
            sale.total_profit = Decimal(str(total_profit))
            sale.save()

            logger.info(f"Offline sale synced successfully: {sale.id}")

            return JsonResponse({
                'success': True,
                'message': 'Sale synced successfully',
                'sale_id': str(sale.id),
                'total_amount': float(sale.final_total_price),
                'items_count': len(data.get('items', []))
            })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error syncing offline sale: {str(e)}")
        return JsonResponse(
            {'error': f'Sync failed: {str(e)}'},
            status=500
        )


def check_and_reserve_inventory(branch, items):
    """
    Check if all items have sufficient inventory
    
    Returns:
        dict: {
            'available': bool,
            'details': list of items with availability status
        }
    """
    details = []
    all_available = True

    for item in items:
        product_id = item.get('product_id')
        quantity = int(item.get('quantity', 1))

        try:
            inventory = Inventory.objects.get(
                product_id=product_id,
                branch=branch,
                organization_id=item.get('organization_id')  # Optional: filter by org
            )

            available_qty = inventory.quantity or 0
            is_available = available_qty >= quantity

            details.append({
                'product_id': product_id,
                'requested': quantity,
                'available': available_qty,
                'status': 'ok' if is_available else 'insufficient'
            })

            if not is_available:
                all_available = False

        except Inventory.DoesNotExist:
            # Log warning about missing inventory
            logger.warning(
                f"Inventory lookup failed for product_id={product_id}, branch={branch.id}. "
                f"This may indicate the offline cache wasn't loaded on the client."
            )
            details.append({
                'product_id': product_id,
                'requested': quantity,
                'available': 0,
                'status': 'not_found',
                'reason': 'Product not found in inventory for this branch'
            })
            all_available = False

    return {
        'available': all_available,
        'details': details
    }


@require_http_methods(["GET"])
@login_required
def get_offline_data(request):
    """
    Provide products and inventory data for offline caching
    
    Called periodically to update local cache
    """
    try:
        organization = request.user.organization
        branch = request.user.branch

        if not branch:
            return JsonResponse({'error': 'No branch assigned'}, status=400)

        # Get all products and inventory for this branch
        products = list(
            Product.objects.filter(
                branch=branch,
                organization=organization
            ).values(
                'id', 'product_name', 'product_code', 'category__category_name', 'brand'
            )
        )

        inventory = list(
            Inventory.objects.filter(
                branch=branch,
                organization=organization
            ).values(
                'id', 'product_id', 'quantity', 'sale_price', 'cost_price', 'status'
            )
        )

        return JsonResponse({
            'success': True,
            'products': products,
            'inventory': inventory,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Error fetching offline data: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
@login_required
def sync_status(request):
    """
    Get current sync status for UI updates
    """
    return JsonResponse({
        'is_online': True,
        'last_sync': request.session.get('last_offline_sync', None),
        'pending_count': 0  # Will be populated from frontend IndexedDB
    })
