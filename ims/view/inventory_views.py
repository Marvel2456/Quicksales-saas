from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect
from django.contrib import messages
from datetime import datetime, date
from ims.models import Category, Product, Sale, SalesItem, Inventory, ErrorTicket, RestockRequest
from account.models import CustomUser, Branch, ActivityLog
from django.contrib.auth.decorators import login_required
from ims.forms import *
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
import csv
import json
from account.decorators import role_required
from account.utils import get_request_organization, get_request_org_role
from django.template.loader import get_template
from xhtml2pdf import pisa
from ims.view_caching import cached_view
from django.core.cache import cache
from ims.services.inventory import InventoryService



@role_required(roles=['owner'])
@login_required
def branch_inventory(request):
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
    return render(request, 'ims/branch_inv.html', context)



# @cached_view(timeout=300, key_prefix='inventory_list')
@role_required(roles=['owner', 'manager'], permission='inventory')
@login_required
# @is_unsubscribed
def inventory_list(request, pk):
    """Inventory list view - optimized with select_related and proper pagination"""
    organization = get_request_organization(request)
    # Use select_related to fetch branch in single query
    branch = Branch.objects.select_related('organization').get(organization=organization, id=pk)
    
    product_contains_query = request.GET.get('product')
    
    # Delegate query to Service Layer
    inventory_qs = InventoryService.get_inventory(
        organization=organization,
        branch=branch,
        product_name=product_contains_query
    )
    
    # Get products for this branch with select_related
    product = Product.objects.filter(branch=branch).select_related('category', 'branch')
    
    # Paginate FILTERED queryset
    paginator = Paginator(inventory_qs, 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" * inventory_page.paginator.num_pages
    
    import json
    product_variations_map = {
        str(p.id): p.variation_options
        for p in product
        if p.variation_options
    }
    product_variations_json = (
        json.dumps(product_variations_map)
        .replace('<', '\\u003c')
        .replace('>', '\\u003e')
        .replace('&', '\\u0026')
    )

    form = CreateInventoryForm
    if request.method == "POST":
        form = CreateInventoryForm(request.POST)
        if form.is_valid():
            invenvtory_instance = form.save(commit=False)
            invenvtory_instance.branch = branch
            invenvtory_instance.organization = organization
            if invenvtory_instance.reorder_level is None:
                invenvtory_instance.reorder_level = 0
            if request.POST.get('use_variation_quantities') == 'on':
                var_names = request.POST.getlist('variation_name[]')
                var_qtys = request.POST.getlist('variation_qty[]')
                vq = {}
                for raw_name, raw_qty in zip(var_names, var_qtys):
                    vname = (raw_name or '').strip()[:120]
                    if not vname:
                        continue
                    try:
                        vqty = max(0, int(raw_qty or 0))
                    except (ValueError, TypeError):
                        vqty = 0
                    vq[vname] = vq.get(vname, 0) + vqty
                if vq:
                    total_qty = sum(vq.values())
                    invenvtory_instance.variation_quantities = vq
                    invenvtory_instance.quantity = total_qty
                    invenvtory_instance.quantity_available = total_qty
                    invenvtory_instance.status = 'Available' if total_qty > 0 else 'Restocking'
                    if invenvtory_instance.product and not invenvtory_instance.product.variation:
                        invenvtory_instance.product.variation = ", ".join(vq.keys())[:255]
                        invenvtory_instance.product.save(update_fields=['variation'])
                else:
                    invenvtory_instance.status = 'Available' if (invenvtory_instance.quantity or 0) > 0 else 'Restocking'
            else:
                invenvtory_instance.status = 'Available' if (invenvtory_instance.quantity or 0) > 0 else 'Restocking'
            invenvtory_instance.save()
            messages.success(request, 'successfully created')
            # Invalidate inventory list cache for this organization
            if hasattr(cache, 'keys'):
                for key_pattern in cache.keys(f"inventory_list:org:{organization.id}:*"):
                    cache.delete(key_pattern)
            return redirect('inventorys', pk=branch.id)
        else:
            error_parts = []
            for field_name, errs in form.errors.items():
                label = field_name.replace('_', ' ').title()
                error_parts.append(f"{label}: {', '.join(errs)}")
            messages.error(request, 'Could not create inventory. ' + ' | '.join(error_parts))

    pending_restock_count = RestockRequest.objects.filter(
        organization=organization,
        branch=branch,
        status__in=['pending', 'partially_supplied']
    ).count()

    context = {
        'branch': branch,
        'inventory': inventory_qs,
        'product': product,
        'product_variations_json': product_variations_json,
        'form': form,
        'inventory_page': inventory_page,
        'nums': nums,
        'org_role': get_request_org_role(request, organization),
        'pending_restock_count': pending_restock_count,
    }
    return render(request, 'ims/inventory.html', context)





@role_required(roles=['owner'])
@login_required
# @is_unsubscribed
def branchInventory(request):
    """Admin branch inventory view - optimized with select_related"""
    product_contains_query = request.GET.get('product')
    branch_contains_query = request.GET.get('branch')
    
    # Delegate query to Service Layer
    inventory_qs = InventoryService.get_inventory(
        organization=organization,
        product_name=product_contains_query
    )
    if branch_contains_query:
        inventory_qs = inventory_qs.filter(branch__name__icontains=branch_contains_query)
        
    inventory_qs = inventory_qs.order_by('branch')
    
    product = Product.objects.select_related('category', 'branch').filter(organization=organization)
    branch = Branch.objects.select_related('organization').filter(organization=organization)
    
    # Paginate FILTERED queryset
    paginator = Paginator(inventory_qs, 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" * inventory_page.paginator.num_pages
    
    form = AdminCreateInventoryForm
    if request.method == "POST":
        form = AdminCreateInventoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'successfully created')
            return redirect('branchinv')

    context = {
        'inventory': inventory_qs,
        'product': product,
        'branch': branch,
        'form': form,
        'inventory_page': inventory_page,
        'nums': nums,
    }

    return render(request, 'ims/branch_inv.html', context)



@role_required(roles=['owner'])
def inventory(request, pk):
    organization = get_request_organization(request)
    inventory = get_object_or_404(Inventory, id=pk, organization=organization)

    context = {
        'inventory':inventory
    }
    return render(request, 'modals/set_reoder.html', context)


@role_required(roles=['owner'])
def edit_inventory(request, pk):
    organization = get_request_organization(request)
    inventory = get_object_or_404(Inventory, id=pk, organization=organization)
    if request.method == 'POST':
        raw_reorder = request.POST.get('reorder_level')
        if raw_reorder is not None and str(raw_reorder).strip() != '':
            try:
                inventory.reorder_level = max(0, int(raw_reorder))
            except (ValueError, TypeError):
                pass

        use_var_qty = request.POST.get('use_variation_quantities') in ('on', 'true', '1')
        if use_var_qty:
            var_names = request.POST.getlist('variation_name[]')
            var_qtys = request.POST.getlist('variation_qty[]')
            vq = {}
            for raw_name, raw_qty in zip(var_names, var_qtys):
                vname = (raw_name or '').strip()
                if not vname:
                    continue
                try:
                    vqty = max(0, int(raw_qty or 0))
                except (ValueError, TypeError):
                    vqty = 0
                vq[vname] = vq.get(vname, 0) + vqty

            inventory.variation_quantities = vq
            if vq:
                total_qty = sum(vq.values())
                inventory.quantity = total_qty
                inventory.quantity_available = total_qty
                inventory.status = 'Available' if total_qty > 0 else 'Restocking'
                # Sync product variation labels if new variations were added
                existing_opts = inventory.product.variation_options
                merged_opts = list(existing_opts)
                for vn in vq.keys():
                    if vn not in merged_opts:
                        merged_opts.append(vn)
                if merged_opts != existing_opts:
                    inventory.product.variation = ', '.join(merged_opts)
                    inventory.product.save(update_fields=['variation'])
        else:
            inventory.variation_quantities = {}
            raw_qty = request.POST.get('quantity')
            if raw_qty is not None and str(raw_qty).strip() != '':
                try:
                    total_qty = max(0, int(raw_qty))
                    inventory.quantity = total_qty
                    inventory.quantity_available = total_qty
                    inventory.status = 'Available' if total_qty > 0 else 'Restocking'
                except (ValueError, TypeError):
                    pass

        inventory.save()
        if hasattr(cache, 'keys'):
            cache.delete_many(cache.keys(f'inventory_branch_{inventory.branch.id}_*'))
        messages.success(request, 'Inventory updated successfully')
        return redirect('inventorys', pk=inventory.branch.id)

    return redirect('inventorys', pk=inventory.branch.id)


@role_required(roles=['owner', 'manager'], permission='inventory')
def restock(request, pk):
    organization = get_request_organization(request)
    inventory = get_object_or_404(Inventory, id=pk, organization=organization)
    if request.method == 'POST':
        form = RestockForm(request.POST, instance=inventory)
        if form.is_valid():
            restocked_inventory = form.save(commit=False)
            var_names = request.POST.getlist('restock_var_name[]')
            var_qtys = request.POST.getlist('restock_var_qty[]')
            if inventory.has_variation_quantities and var_names:
                vq = dict(inventory.variation_quantities)
                added_total = 0
                for raw_name, raw_qty in zip(var_names, var_qtys):
                    vname = (raw_name or '').strip()
                    if not vname:
                        continue
                    try:
                        add_q = max(0, int(raw_qty or 0))
                    except (ValueError, TypeError):
                        add_q = 0
                    vq[vname] = int(vq.get(vname, 0) or 0) + add_q
                    added_total += add_q
                restocked_inventory.variation_quantities = vq
                restocked_inventory.quantity = sum(vq.values())
                restocked_inventory.quantity_available = restocked_inventory.quantity
                restocked_inventory.quantity_restocked = added_total
                restocked_inventory.status = 'Available' if restocked_inventory.quantity > 0 else 'Restocking'
            else:
                restocked_inventory.quantity += restocked_inventory.quantity_restocked
                restocked_inventory.quantity_restocked = restocked_inventory.quantity_restocked or 0
            restocked_inventory.save()
            # Reset quantity_restocked to zero so future non-restock saves (e.g., sales) don't carry old restock values into history
            Inventory.objects.filter(id=restocked_inventory.id).update(quantity_restocked=0)
            messages.success(request, 'Successfully updated')
            return redirect('inventorys', pk=restocked_inventory.branch.id)
    else:
        form = RestockForm(instance=inventory)

    context = {
        'form': form,
        'inventory': inventory,
        'branch': inventory.branch,
    }
    return render(request, 'modals/restock.html', context)


@role_required(roles=['owner', 'manager'])
@login_required
# @is_unsubscribed
def inventoryView(request, pk):
    organization = get_request_organization(request)
    branch = get_object_or_404(Branch, id=pk, organization=organization)
    product_contains_query = request.GET.get('product')
    
    # Delegate query to Service Layer
    inventory = InventoryService.get_inventory(
        organization=organization,
        branch=branch,
        product_name=product_contains_query
    )
    product = Product.objects.filter(branch=branch, organization=organization)
    
    paginator = Paginator(inventory, 15)
    page = request.GET.get('page')
    inventory_page = paginator.get_page(page)
    nums = "a" *inventory_page.paginator.num_pages

    context = {
        'branch':branch,
        'inventory':inventory,
        'product':product,
        'inventory_page':inventory_page,
        'nums':nums,
    }
    return render(request, 'ims/product_list.html', context)


@role_required(roles=['owner'])
def delete_inventory(request, pk):
    organization = get_request_organization(request)
    inventory = get_object_or_404(Inventory, id=pk, organization=organization)
    branch_id = inventory.branch.id
    if request.method == 'POST':
        product_name = inventory.product.product_name
        inventory.delete()
        if hasattr(cache, 'keys'):
            cache.delete_many(cache.keys(f'inventory_branch_{branch_id}_*'))
        messages.success(request, f'Inventory for "{product_name}" deleted successfully.')
    return redirect('inventorys', pk=branch_id)



