from datetime import datetime, date
from django.db.models import Sum, Count, Q, F
from ims.models import Inventory, Category, Product, ErrorTicket

class InventoryService:
    @staticmethod
    def get_inventory(organization, branch=None, product_name=None, status=None):
        """
        Generic filter queries for branch/organization inventory.
        """
        qs = Inventory.objects.filter(organization=organization).select_related('product', 'branch', 'organization')
        if branch:
            qs = qs.filter(branch=branch)
        if product_name:
            qs = qs.filter(
                Q(product__product_name__icontains=product_name) |
                Q(product__product_code__icontains=product_name)
            )
        if status:
            qs = qs.filter(status=status)
            
        return qs.order_by('-last_updated')

    @staticmethod
    def get_inventory_summary(organization, branch=None):
        """
        Calculates simple counts for products, categories, low stock, and pending errors.
        """
        products = Product.objects.filter(organization=organization)
        categories = Category.objects.filter(organization=organization)
        pending_tickets = ErrorTicket.objects.filter(organization=organization, status='Pending')
        inventory = Inventory.objects.filter(organization=organization)
        
        if branch:
            products = products.filter(branch=branch)
            categories = categories.filter(branch=branch)
            pending_tickets = pending_tickets.filter(branch=branch)
            inventory = inventory.filter(branch=branch)
            
        total_product = products.count()
        total_category = categories.count()
        pending_errors = pending_tickets.count()
        
        # Low stock items (where quantity <= reorder_level)
        low_stock_count = inventory.filter(quantity__lte=F('reorder_level')).count()
        
        return {
            'total_product': total_product,
            'total_category': total_category,
            'pending_errors': pending_errors,
            'low_stock_count': low_stock_count,
        }

    @staticmethod
    def get_low_stock_items(organization, branch=None):
        """
        Fetches inventory items that are at or below reorder levels.
        """
        qs = Inventory.objects.filter(organization=organization, quantity__lte=F('reorder_level')).select_related('product', 'branch')
        if branch:
            qs = qs.filter(branch=branch)
        return qs.order_by('quantity')

    @staticmethod
    def get_variance_statistics(organization, branch, product_name=None):
        """
        Calculates inventory count variance (expected system vs physical counts).
        """
        inventory_items = Inventory.objects.filter(branch=branch, organization=organization).select_related('product', 'branch')
        
        if product_name:
            inventory_items = inventory_items.filter(
                Q(product__product_name__icontains=product_name) |
                Q(product__product_code__icontains=product_name)
            )
        
        total_items = inventory_items.count()
        total_items_counted = 0
        items_with_variance = 0
        total_variance_qty = 0
        inventory_with_variance = []
        
        for item in inventory_items:
            # Note: store_quantity is a model property executing aggregates,
            # so we access it directly.
            store_qty = item.store_quantity
            
            if item.count is not None:
                total_items_counted += 1
                variance = item.count - store_qty
                variance_pct = (variance / store_qty * 100) if store_qty > 0 else 0
                
                if variance != 0:
                    items_with_variance += 1
                    total_variance_qty += abs(variance)
                    
                variance_status = 'danger' if variance > 0 else ('warning' if variance < 0 else 'success')
            else:
                variance = None
                variance_pct = None
                variance_status = 'secondary'
                
            inventory_with_variance.append({
                'item': item,
                'variance': variance,
                'variance_pct': variance_pct,
                'variance_status': variance_status
            })
            
        return {
            'total_items': total_items_counted,  # Number of items actually counted
            'total_inventory_items': total_items,
            'items_with_variance': items_with_variance,
            'total_variance_qty': total_variance_qty,
            'inventory': inventory_with_variance
        }

    @staticmethod
    def get_stock_audit_trail(organization, branch=None, start_date=None, end_date=None, product_name=None):
        """
        Retrieves restock history using HistoricalRecords.
        """
        audits = Inventory.history.filter(organization=organization, quantity_restocked__gt=0)
        if branch:
            audits = audits.filter(branch_id=branch.id)
            
        if product_name:
            audits = audits.filter(product__product_name__icontains=product_name)
        if start_date:
            audits = audits.filter(history_date__date__gte=start_date)
        if end_date:
            audits = audits.filter(history_date__date__lte=end_date)
            
        return audits.order_by('-history_date')
