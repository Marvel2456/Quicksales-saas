from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect
from django.contrib import messages
from datetime import datetime, date
from ims.models import Category, Product, Sale, SalesItem, Inventory, ErrorTicket
from account.models import CustomUser, Branch, ActivityLog, Notification
from django.contrib.auth.decorators import login_required
from ims.forms import *
import uuid
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
import csv
import json
from account.decorators import role_required, check_product_limit
from account.utils import get_request_branch, get_request_organization
from django.template.loader import get_template
from xhtml2pdf import pisa
from ims.view_caching import cached_view
from django.core.cache import cache


# Helper function to create notifications
def create_notification(user, message, notification_type='info', organization=None):
    """Create a notification for a user"""
    Notification.objects.create(
        user=user,
        message=message,
        notification_type=notification_type,
        organization=organization
    )


# Write your views here.

@role_required(roles=['owner'])
@login_required
def branch_product(request):
    # Use organization from middleware context (supports multi-org)
    organization = get_request_organization(request)
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
    return render(request, 'ims/branch_product.html', context)

# @cached_view(timeout=300, key_prefix='product_list')
@role_required(roles=['owner', 'manager'])
@login_required
@check_product_limit
def product_category(request, pk):
    """Product list view - optimized with select_related and proper pagination"""
    organization = get_request_organization(request)
    # Use select_related to fetch branch in single query
    branch = Branch.objects.select_related('organization').get(organization=organization, id=pk)
    
    # Use select_related for efficient product and category loading
    product_qs = Product.objects.filter(branch=branch).select_related(
        'category', 'branch', 'organization'
    ).order_by('-created_at')
    
    # Get categories for this branch with select_related
    category = Category.objects.filter(branch=branch).select_related('branch', 'organization')
    
    # Apply product filter if provided
    product_contains = request.GET.get('product_name')
    if product_contains:
        product_qs = product_qs.filter(product_name__icontains=product_contains)
    
    # Paginate FILTERED queryset
    paginator = Paginator(product_qs, 15)
    page = request.GET.get('page')
    products_page = paginator.get_page(page)
    nums = "a" * products_page.paginator.num_pages
    
    form = ProductForm(organization=organization, branch=branch)
    if request.method == "POST":
        form = ProductForm(request.POST, organization=organization, branch=branch)
        if form.is_valid():
            product_instance = form.save(commit=False)
            product_instance.branch = branch
            product_instance.organization = organization
            product_instance.save()
            messages.success(request, 'successfully created')
            # Invalidate product list cache for this organization
            for key_pattern in cache.keys(f"product_list:org:{organization.id}:*"):
                cache.delete(key_pattern)
            return redirect('products', pk=branch.id)
        
    context = {
        'category': category,
        'form': form,
        'product': product_qs,
        'products_page': products_page,
        'nums': nums,
        'branch': branch
    }
    return render(request, 'ims/products.html', context)


# @cached_view(timeout=600, key_prefix='product_detail')
@role_required(roles=['owner'])
def product(request, pk):
    organization = get_request_organization(request)
    products = get_object_or_404(Product, id=pk, organization=organization)

    context = {
        'products':products
    } 
    return render(request, 'modals/modal_edit_product.html', context)


@role_required(roles=['owner'])
def edit_product(request, pk):
    """Edit product view - optimized with select_related"""
    organization = get_request_organization(request)
    # Use select_related to fetch related branch
    product = get_object_or_404(
        Product.objects.select_related('category', 'branch', 'organization'),
        id=pk,
        organization=organization
    )

    if request.method == 'POST':
        form = EditProductForm(request.POST, instance=product, organization=organization, branch=product.branch)
        if form.is_valid():
            updated_product = form.save()
            messages.success(request, 'Successfully updated')
            return redirect('products', pk=updated_product.branch.id)
    else:
        form = EditProductForm(instance=product, organization=organization, branch=product.branch)

    # Use select_related for categories
    categories = Category.objects.filter(
        organization=organization,
        branch=product.branch
    ).select_related('branch', 'organization')

    context = {
        'form': form,
        'product': product,
        'categories': categories,
    }
    return render(request, 'modals/modal_edit_product.html', context)

        

@role_required(roles=['owner'])
def delete_product(request, pk):
    organization = get_request_organization(request)
    
    if request.method == 'POST':
        product = get_object_or_404(Product, id=pk, organization=organization)
        branch_id = product.branch.id 
        product.delete()
        messages.success(request, "Successfully deleted")
        return redirect('products', pk=branch_id)



@role_required(roles=['owner'])
@login_required
def upload_product(request):
    """Owner creates or updates products and inventory for their branch.
    
    Supports both file upload (CSV/Excel with multiple products) and manual entry.
    """
    import pandas as pd
    import io
    
    organization = get_request_organization(request)
    branch = get_request_branch(request, organization)
    if not branch:
        messages.error(request, 'You need an assigned branch to upload products.')
        return redirect('index')

    form = UploadProductForm(organization=organization)
    if request.method == 'POST':
        form = UploadProductForm(request.POST, request.FILES, organization=organization)
        if form.is_valid():
            upload_file = request.FILES.get('upload_file')
            
            if upload_file:
                # Handle bulk file upload
                try:
                    # Read file based on extension
                    file_ext = upload_file.name.split('.')[-1].lower()
                    
                    if file_ext == 'csv':
                        df = pd.read_csv(io.BytesIO(upload_file.read()))
                    elif file_ext in ['xlsx', 'xls']:
                        df = pd.read_excel(io.BytesIO(upload_file.read()))
                    else:
                        messages.error(request, 'Invalid file format. Please upload CSV or Excel file.')
                        return redirect('product_upload')
                    
                    # Process each row
                    created_count = 0
                    updated_count = 0
                    error_count = 0
                    errors = []
                    
                    for index, row in df.iterrows():
                        try:
                            # Get or create category
                            category_name = str(row.get('category', '')).strip()
                            if not category_name:
                                errors.append(f"Row {index + 2}: Category name is required")
                                error_count += 1
                                continue
                            
                            # Get or create category (case-insensitive)
                            category = Category.objects.filter(
                                organization=organization,
                                branch=branch,
                                category_name__iexact=category_name
                            ).first()
                            
                            if not category:
                                category = Category.objects.create(
                                    organization=organization,
                                    branch=branch,
                                    category_name=category_name
                                )
                                messages.info(request, f"New category '{category_name}' created.")
                            
                            product_name = str(row.get('product_name', '')).strip()
                            if not product_name:
                                errors.append(f"Row {index + 2}: Product name is required")
                                error_count += 1
                                continue
                            
                            # Get or create product
                            product = Product.objects.filter(
                                organization=organization,
                                product_name__iexact=product_name
                            ).first()
                            
                            if product:
                                # Update existing product
                                product.category = category
                                product.brand = str(row.get('brand', '')).strip()
                                product.unit = str(row.get('unit', '')).strip()
                                product.batch_no = str(row.get('batch_no', '')).strip()
                                product.save()
                                is_new_product = False
                            else:
                                # Create new product
                                product = Product.objects.create(
                                    organization=organization,
                                    branch=branch,
                                    product_name=product_name,
                                    category=category,
                                    brand=str(row.get('brand', '')).strip(),
                                    unit=str(row.get('unit', '')).strip(),
                                    batch_no=str(row.get('batch_no', '')).strip(),
                                    product_code=str(uuid.uuid4())[:8].upper(),
                                )
                                is_new_product = True
                            
                            # Handle inventory
                            try:
                                cost_price = float(row.get('cost_price', 0))
                                sale_price = float(row.get('sale_price', 0))
                                quantity = int(row.get('quantity', 0))
                                reorder_level = int(row.get('reorder_level', 0))
                            except (ValueError, TypeError):
                                errors.append(f"Row {index + 2}: Invalid price or quantity values")
                                error_count += 1
                                continue
                            
                            added_qty = max(quantity, 0)
                            inventory, inv_created = Inventory.objects.get_or_create(
                                organization=organization,
                                branch=branch,
                                product=product,
                                defaults={
                                    'quantity': added_qty,
                                    'cost_price': cost_price,
                                    'sale_price': sale_price,
                                    'reorder_level': reorder_level,
                                    'status': 'Available' if added_qty > 0 else 'Restocking',
                                    'quantity_restocked': added_qty,
                                }
                            )
                            
                            if not inv_created:
                                inventory.quantity_restocked = added_qty
                                inventory.quantity = (inventory.quantity or 0) + added_qty
                                inventory.cost_price = cost_price
                                inventory.sale_price = sale_price
                                inventory.reorder_level = reorder_level
                                inventory.status = 'Available' if inventory.quantity > 0 else 'Restocking'
                                inventory.save()

                            # Reset quantity_restocked so subsequent non-restock saves (e.g., sales) don't carry this value
                            Inventory.objects.filter(id=inventory.id).update(quantity_restocked=0)
                            inventory.quantity_restocked = 0
                            
                            if is_new_product:
                                created_count += 1
                            else:
                                updated_count += 1
                                
                        except Exception as e:
                            errors.append(f"Row {index + 2}: {str(e)}")
                            error_count += 1
                    
                    # Display results
                    if created_count > 0:
                        msg = f'Successfully created {created_count} product(s).'
                        messages.success(request, msg)
                        create_notification(request.user, msg, 'success', organization)
                    if updated_count > 0:
                        msg = f'Successfully updated {updated_count} product(s).'
                        messages.success(request, msg)
                        create_notification(request.user, msg, 'success', organization)
                    if error_count > 0:
                        warn_msg = f'{error_count} row(s) had errors.'
                        messages.warning(request, warn_msg)
                        create_notification(request.user, warn_msg, 'warning', organization)
                        for error in errors[:5]:  # Show first 5 errors
                            messages.error(request, error)
                            create_notification(request.user, error, 'error', organization)
                        if len(errors) > 5:
                            info_msg = f'...and {len(errors) - 5} more errors'
                            messages.info(request, info_msg)
                            create_notification(request.user, info_msg, 'info', organization)
                    
                    return redirect('products', pk=branch.id)
                    
                except Exception as e:
                    err_msg = f'Error processing file: {str(e)}'
                    messages.error(request, err_msg)
                    create_notification(request.user, err_msg, 'error', organization)
                    return redirect('product_upload')
            
            else:
                # Handle manual single product entry
                data = form.cleaned_data
                product_name = data['product_name'].strip()
                category = data['category']
                brand = data.get('brand')
                unit = data.get('unit')
                batch_no = data.get('batch_no')
                cost_price = data['cost_price']
                sale_price = data['sale_price']
                qty = data['quantity']
                reorder_level = data.get('reorder_level') or 0

                # Find or create product scoped to organization
                product = Product.objects.filter(organization=organization, product_name__iexact=product_name).first()
                created = False
                if product is None:
                    product = Product(
                        organization=organization,
                        branch=branch,
                        product_name=product_name,
                        category=category,
                        brand=brand,
                        unit=unit,
                        batch_no=batch_no,
                        product_code=f"{uuid.uuid4().hex[:8]}"
                    )
                    product.save()
                    created = True
                else:
                    # Update metadata if changed
                    product.branch = branch
                    product.category = category
                    product.brand = brand
                    product.unit = unit
                    product.batch_no = batch_no
                    product.save()

                # Inventory per branch + product
                added_qty = max(qty, 0)
                inventory, inv_created = Inventory.objects.get_or_create(
                    organization=organization,
                    branch=branch,
                    product=product,
                    defaults={
                        'quantity': added_qty,
                        'cost_price': cost_price,
                        'sale_price': sale_price,
                        'reorder_level': reorder_level,
                        'status': 'Available' if added_qty > 0 else 'Restocking',
                        'quantity_restocked': added_qty,
                    }
                )

                if not inv_created:
                    # Increment quantity and update prices/levels
                    inventory.quantity_restocked = added_qty
                    inventory.quantity = (inventory.quantity or 0) + added_qty
                    inventory.cost_price = cost_price
                    inventory.sale_price = sale_price
                    inventory.reorder_level = reorder_level
                    inventory.status = 'Available' if inventory.quantity > 0 else 'Restocking'
                    inventory.save()

                # Reset quantity_restocked so future saves (like sales) don't look like restocks
                Inventory.objects.filter(id=inventory.id).update(quantity_restocked=0)

                messages.success(
                    request,
                    'Product {} and inventory {} successfully.'.format(
                        'created' if created else 'updated',
                        'initialized' if inv_created else 'updated'
                    )
                )
                return redirect('products', pk=branch.id)
        else:
            messages.error(request, 'Please correct the form errors.')

    context = {
        'form': form,
        'branch': branch,
    }
    return render(request, 'ims/product_upload.html', context)
