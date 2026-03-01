from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.template.loader import get_template
from xhtml2pdf import pisa
from datetime import datetime, date
import json

from ims.models import Invoice, InvoiceItem, Inventory, Sale, SalesItem
from account.models import Branch, CustomUser, Notification
from account.decorators import role_required
from account.utils import get_request_organization


def _generate_invoice_number(organization):
    """Generate a unique invoice number like INV-20240227-0001"""
    today = date.today().strftime('%Y%m%d')
    count = Invoice.objects.filter(
        organization=organization,
        date_created__date=date.today()
    ).count() + 1
    return f"INV-{today}-{count:04d}"


@role_required(roles=['owner'])
@login_required
def branch_invoices(request):
    """Branch selector for invoices (owner only)"""
    organization = get_request_organization(request)
    branch_qs = Branch.objects.filter(organization=organization)

    paginator = Paginator(branch_qs, 15)
    page = request.GET.get('page')
    branch_page = paginator.get_page(page)
    nums = range(1, branch_page.paginator.num_pages + 1)

    branch_contains_query = request.GET.get('branch')
    if branch_contains_query:
        branch_page = branch_qs.filter(name__icontains=branch_contains_query)

    context = {
        'branch': branch_qs,
        'branch_page': branch_page,
        'nums': nums,
    }
    return render(request, 'ims/branchinvoices.html', context)


@role_required(roles=['owner'])
@login_required
def invoices(request, pk):
    """List all invoices for a branch with filtering"""
    organization = get_request_organization(request)
    branch = get_object_or_404(Branch, organization=organization, id=pk)

    invoice_qs = Invoice.objects.filter(
        branch=branch,
        organization=organization
    ).select_related('created_by').order_by('-date_created')

    # Filters
    status_filter = request.GET.get('status')
    customer_query = request.GET.get('customer')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if status_filter:
        invoice_qs = invoice_qs.filter(status=status_filter)
    if customer_query:
        invoice_qs = invoice_qs.filter(customer_name__icontains=customer_query)
    if start_date:
        invoice_qs = invoice_qs.filter(date_created__date__gte=start_date)
    if end_date:
        invoice_qs = invoice_qs.filter(date_created__date__lte=end_date)

    paginator = Paginator(invoice_qs, 15)
    page = request.GET.get('page')
    invoice_page = paginator.get_page(page)
    nums = range(1, invoice_page.paginator.num_pages + 1)

    context = {
        'branch': branch,
        'invoice_page': invoice_page,
        'nums': nums,
        'status_filter': status_filter,
        'customer_query': customer_query,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'ims/invoices.html', context)


@role_required(roles=['owner'])
@login_required
def create_invoice(request, pk):
    """Create a new invoice for a branch"""
    organization = get_request_organization(request)
    branch = get_object_or_404(Branch, organization=organization, id=pk)
    inventory_qs = Inventory.objects.filter(
        branch=branch, organization=organization
    ).select_related('product').order_by('product__product_name')

    if request.method == 'POST':
        customer_name = request.POST.get('customer_name', '').strip()
        customer_email = request.POST.get('customer_email', '').strip()
        customer_phone = request.POST.get('customer_phone', '').strip()
        notes = request.POST.get('notes', '').strip()
        due_date = request.POST.get('due_date') or None
        payment_method = request.POST.get('payment_method', '')

        # Parse line items from POST
        inventory_ids = request.POST.getlist('inventory_id[]')
        quantities = request.POST.getlist('quantity[]')

        if not inventory_ids or not any(quantities):
            messages.error(request, 'Please add at least one item to the invoice.')
            return render(request, 'ims/create_invoice.html', {
                'branch': branch, 'inventory': inventory_qs
            })

        # Create the invoice
        invoice = Invoice.objects.create(
            organization=organization,
            branch=branch,
            created_by=request.user,
            customer_name=customer_name or None,
            customer_email=customer_email or None,
            customer_phone=customer_phone or None,
            notes=notes or None,
            due_date=due_date,
            payment_method=payment_method or None,
            invoice_number=_generate_invoice_number(organization),
            status='pending',
        )

        total = 0.0
        for inv_id, qty in zip(inventory_ids, quantities):
            try:
                inventory = Inventory.objects.get(id=inv_id, branch=branch, organization=organization)
                qty_int = int(qty) if qty else 0
                if qty_int <= 0:
                    continue
                unit_price = inventory.sale_price or 0.0
                item_total = unit_price * qty_int
                InvoiceItem.objects.create(
                    invoice=invoice,
                    organization=organization,
                    branch=branch,
                    inventory=inventory,
                    quantity=qty_int,
                    unit_price=unit_price,
                    total=item_total,
                )
                total += item_total
            except Inventory.DoesNotExist:
                continue

        invoice.total_amount = total
        invoice.save()

        messages.success(request, f'Invoice {invoice.invoice_number} created successfully.')
        return redirect('invoice_detail', pk=invoice.id)

    context = {
        'branch': branch,
        'inventory': inventory_qs,
    }
    return render(request, 'ims/create_invoice.html', context)


@role_required(roles=['owner'])
@login_required
def invoice_detail(request, pk):
    """View a single invoice with all its items"""
    organization = get_request_organization(request)
    invoice = get_object_or_404(Invoice, id=pk, organization=organization)
    items = invoice.items.select_related('inventory__product').all()

    context = {
        'invoice': invoice,
        'items': items,
        'branch': invoice.branch,
    }
    return render(request, 'ims/invoice_detail.html', context)


@role_required(roles=['owner'])
@login_required
def invoice_pdf(request, pk):
    """Download invoice as PDF"""
    organization = get_request_organization(request)
    invoice = get_object_or_404(Invoice, id=pk, organization=organization)
    items = invoice.items.select_related('inventory__product').all()

    template_path = 'ims/invoice_pdf.html'
    context = {
        'invoice': invoice,
        'items': items,
        'branch': invoice.branch,
        'organization': organization,
    }
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'filename="Invoice_{invoice.invoice_number}.pdf"'
    template = get_template(template_path)
    html = template.render(context)
    pisa_status = pisa.CreatePDF(html, dest=response, encoding='utf-8')
    if pisa_status.err:
        return HttpResponse('Error generating PDF. <pre>' + html + '</pre>')
    return response


@role_required(roles=['owner'])
@login_required
def confirm_payment(request, pk):
    """Confirm payment: mark invoice as paid, deduct inventory, create Sale record"""
    organization = get_request_organization(request)
    invoice = get_object_or_404(Invoice, id=pk, organization=organization)

    if invoice.status != 'pending':
        messages.error(request, 'Only pending invoices can be confirmed.')
        return redirect('invoice_detail', pk=invoice.id)

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', invoice.payment_method or 'Cash')
        
        try:
            # Deduct inventory for each item
            items = invoice.items.select_related('inventory').all()
            for item in items:
                if item.inventory and item.quantity:
                    item.inventory.refresh_from_db()
                    item.inventory.quantity -= item.quantity
                    item.inventory.save()

            # Create a Sale record for reporting continuity
            from datetime import datetime as dt
            import time
            transaction_id = f"INV-PAY-{int(time.time())}"
            sale = Sale.objects.create(
                organization=organization,
                branch=invoice.branch,
                staff=invoice.created_by,
                method=payment_method,
                final_total_price=invoice.total_amount,
                total_profit=0,
                transaction_id=transaction_id,
                completed=True,
            )
            
            total_profit = 0
            for item in items:
                if item.inventory:
                    cost_total = (item.inventory.cost_price or 0) * (item.quantity or 0)
                    total = item.total or 0
                    profit = total - cost_total
                    total_profit += profit
                    
                    SalesItem.objects.create(
                        sale=sale,
                        organization=organization,
                        branch=invoice.branch,
                        inventory=item.inventory,
                        quantity=item.quantity,
                        total=total,
                        cost_total=cost_total,
                    )
            
            # Update sale with actual calculated profit
            sale.total_profit = total_profit
            sale.save()

            # Update invoice status
            invoice.status = 'paid'
            invoice.payment_method = payment_method
            invoice.save()

            # Notify owner if they're not the one doing this
            owner = organization.owned_by
            if owner and owner != request.user:
                Notification.objects.create(
                    user=owner,
                    message=f"Invoice {invoice.invoice_number} confirmed as paid. N{invoice.total_amount:,.2f}",
                    notification_type='success',
                    organization=organization,
                    is_read=False,
                )

            messages.success(request, f'Payment confirmed for invoice {invoice.invoice_number}. Inventory updated.')
            return redirect('invoice_detail', pk=invoice.id)
            
        except Exception as e:
            import traceback
            print(f"ERROR in confirm_payment: {str(e)}")
            print(traceback.format_exc())
            messages.error(request, f'Error confirming payment: {str(e)}')
            return redirect('invoice_detail', pk=invoice.id)

    return redirect('invoice_detail', pk=invoice.id)


@role_required(roles=['owner'])
@login_required
def close_invoice(request, pk):
    """Close an invoice without confirming payment (no inventory change)"""
    organization = get_request_organization(request)
    invoice = get_object_or_404(Invoice, id=pk, organization=organization)

    if invoice.status != 'pending':
        messages.error(request, 'Only pending invoices can be closed.')
        return redirect('invoice_detail', pk=invoice.id)

    if request.method == 'POST':
        invoice.status = 'closed'
        invoice.save()
        messages.success(request, f'Invoice {invoice.invoice_number} has been closed.')
        return redirect('invoices', pk=invoice.branch.id)

    return redirect('invoice_detail', pk=invoice.id)


@role_required(roles=['owner'])
@login_required
def delete_invoice(request, pk):
    """Delete a pending or closed invoice"""
    organization = get_request_organization(request)
    invoice = get_object_or_404(Invoice, id=pk, organization=organization)

    if invoice.status == 'paid':
        messages.error(request, 'Paid invoices cannot be deleted.')
        return redirect('invoice_detail', pk=invoice.id)

    if request.method == 'POST':
        branch_id = invoice.branch.id
        invoice.delete()
        messages.success(request, 'Invoice deleted.')
        return redirect('invoices', pk=branch_id)

    return redirect('invoice_detail', pk=invoice.id)
