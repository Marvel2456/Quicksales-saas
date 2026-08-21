from django.http import JsonResponse
from django.db.models import Q, F
from ims.models import Inventory, Product
from account.models import Branch
from ims.api_decorators import require_api_key

def _get_branch_context(request, organization):
    """
    Helper to extract and validate branch scope from query parameters.
    """
    branch_id = request.GET.get('branch_id')
    branch_name = request.GET.get('branch_name')
    
    if branch_id:
        try:
            return Branch.objects.filter(id=branch_id, organization=organization).first()
        except:
            return None
    elif branch_name:
        return Branch.objects.filter(name__iexact=branch_name, organization=organization).first()
    return None

@require_api_key
def api_inventory_status(request):
    """
    GET /api/v1/inventory/status/
    Returns high-level inventory metrics for the organization or active branch.
    """
    org = request.api_organization
    branch = _get_branch_context(request, org)
    
    inventories = Inventory.objects.filter(organization=org)
    if branch:
        inventories = inventories.filter(branch=branch)
        
    total_skus = inventories.count()
    in_stock = inventories.filter(quantity_available__gt=0, status='Available').count()
    out_of_stock = inventories.filter(Q(quantity_available__lte=0) | Q(status='Restocking')).count()
    low_stock = inventories.filter(quantity_available__lte=F('reorder_level'), reorder_level__gt=0).count()
    
    return JsonResponse({
        'status': 'success',
        'organization': org.name,
        'branch': branch.name if branch else 'All Branches',
        'metrics': {
            'total_skus': total_skus,
            'in_stock': in_stock,
            'out_of_stock': out_of_stock,
            'low_stock': low_stock
        }
    })

@require_api_key
def api_product_list(request):
    """
    GET /api/v1/inventory/products/
    Returns a list of all products in the active branch/organization.
    Supports basic ?search= text filtering.
    """
    org = request.api_organization
    branch = _get_branch_context(request, org)
    
    inventories = Inventory.objects.filter(organization=org).select_related('product', 'product__category', 'branch')
    if branch:
        inventories = inventories.filter(branch=branch)
        
    search_query = request.GET.get('search', '').strip()
    if search_query:
        inventories = inventories.filter(
            Q(product__product_name__icontains=search_query) | 
            Q(product__product_code__icontains=search_query)
        )
        
    products_data = []
    for item in inventories:
        products_data.append({
            'product_name': item.product.product_name,
            'product_code': item.product.product_code,
            'category': item.product.category.category_name,
            'brand': item.product.brand or '',
            'branch': item.branch.name,
            'quantity': item.quantity_available,
            'sale_price': item.sale_price or 0.0,
            'status': item.status
        })
        
    return JsonResponse({
        'status': 'success',
        'organization': org.name,
        'branch': branch.name if branch else 'All Branches',
        'count': len(products_data),
        'products': products_data
    })

@require_api_key
def api_product_detail(request):
    """
    GET /api/v1/inventory/query/
    Looks up a specific product using its code or name.
    Usage: ?code=XYZ or ?query=name
    """
    org = request.api_organization
    branch = _get_branch_context(request, org)
    
    code = request.GET.get('code', '').strip()
    query = request.GET.get('query', '').strip()
    
    if not code and not query:
        return JsonResponse({'error': 'Please provide a product ?code= or ?query= search parameter'}, status=400)
        
    inventories = Inventory.objects.filter(organization=org).select_related('product', 'product__category', 'branch')
    if branch:
        inventories = inventories.filter(branch=branch)
        
    if code:
        inventories = inventories.filter(product__product_code__iexact=code)
    elif query:
        inventories = inventories.filter(product__product_name__icontains=query)
        
    matches = []
    for item in inventories:
        matches.append({
            'product_name': item.product.product_name,
            'product_code': item.product.product_code,
            'category': item.product.category.category_name,
            'brand': item.product.brand or '',
            'branch': item.branch.name,
            'quantity': item.quantity_available,
            'sale_price': item.sale_price or 0.0,
            'status': item.status,
            'reorder_level': item.reorder_level
        })
        
    return JsonResponse({
        'status': 'success',
        'organization': org.name,
        'count': len(matches),
        'matches': matches
    })
