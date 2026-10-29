from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.template.loader import get_template
from django.db import transaction
from django.db.models import F, Q
from xhtml2pdf import pisa
from datetime import datetime, date
import json
import time

from ims.models import (
    Invoice, InvoiceItem, InvoicePayment, InvoiceEditLog,
    Inventory, Sale, SalesItem
)
from account.models import Branch, CustomUser, Notification, ActivityLog
from account.decorators import role_required
from account.utils import (
    get_request_organization, get_request_org_role, get_request_branch
)


def _generate_invoice_number(organization):
    """Generate a unique invoice number like INV-20240227-0001"""
    today = date.today().strftime('%Y%m%d')
    count = Invoice.objects.filter(
        organization=organization,
        date_created__date=date.today()
    ).count() + 1
    return f"INV-{today}-{count:04d}"


def _user_display_With_role(user, organization):
    if not user:
        return "System"
    name = (user.get_full_name() or "").strip()
    if not name or name == "None None":
        name = user.first_name or user.email
    role = user.get_role_in_organization(organization) if organization else getattr(user, 'role', '')
    role_label = role.title() if role else "Staff"
    return f"{name} ({role_label})"


def _record_invoice_log(invoice, user, action, summary):
    """Create both an InvoiceEditLog (for owner audit on the invoice) and an ActivityLog."""
    InvoiceEditLog.objects.create(
        invoice=invoice,
        organization=invoice.organization,
        branch=invoice.branch,
        user=user,
        action=action,
        summary=summary,
    )
    if user and user.is_authenticated:
        ActivityLog.objects.create(
            organization=invoice.organization,
            branch=invoice.branch,
            staff=user,
            activity=f"[Invoice {invoice.invoice_number}] {summary}"[:1000],
        )


def _check_branch_access(request, organization, branch):
    """
    Ensure that a manager can only access invoices for their assigned branch.
    Owners have access to all branches in their organization.
    """
    role = get_request_org_role(request, organization)
    if role == 'owner':
        return True
    if role == 'manager':
        assigned_branch = request.user.get_branch_in_organization(organization) or getattr(request.user, 'branch', None)
        if assigned_branch and str(assigned_branch.id) != str(branch.id):
            messages.error(request, 'You only have permission to access invoices for your assigned branch.')
            return False
        return True
    return False


def _create_completed_sale_for_invoice(invoice, payment_method):
    """Create a completed Sale and SalesItem records once an invoice is fully paid."""
    organization = invoice.organization
    items = invoice.items.select_related('inventory').all()
    transaction_id = f"INV-PAY-{int(time.time())}"
    sale = Sale.objects.create(
        organization=organization,
        branch=invoice.branch,
        staff=invoice.created_by,
        method=payment_method or invoice.payment_method or 'Cash',
        final_total_price=invoice.total_amount,
        total_profit=0,
        transaction_id=transaction_id,
        completed=True,
    )

    total_profit = 0.0
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

    sale.total_profit = total_profit
    sale.save(update_fields=['total_profit'])
    return sale


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


@role_required(roles=['owner', 'manager'])
@login_required
def invoices(request, pk):
    """List all invoices for a branch with filtering (Owner & Manager)"""
    organization = get_request_organization(request)
    branch = get_object_or_404(Branch, organization=organization, id=pk)

    if not _check_branch_access(request, organization, branch):
        user_branch = get_request_branch(request, organization)
        if user_branch:
            return redirect('invoices', pk=user_branch.id)
        return redirect('dashboard')

    # Backfill existing paid invoices so amount_paid matches total_amount
    Invoice.objects.filter(
        branch=branch,
        organization=organization,
        status='paid'
    ).filter(Q(amount_paid__isnull=True) | Q(amount_paid=0)).update(
        amount_paid=F('total_amount'),
        inventory_deducted=True
    )

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


@role_required(roles=['owner', 'manager'])
@login_required
def create_invoice(request, pk):
    """Create a new invoice for a branch (Owner & Manager)"""
    organization = get_request_organization(request)
    branch = get_object_or_404(Branch, organization=organization, id=pk)

    if not _check_branch_access(request, organization, branch):
        user_branch = get_request_branch(request, organization)
        if user_branch:
            return redirect('invoices', pk=user_branch.id)
        return redirect('dashboard')

    inventory_qs = Inventory.objects.filter(
        branch=branch,
        organization=organization,
        product__branch=branch,
        product__organization=organization,
        quantity__gt=0,
    ).select_related('product').order_by('product__product_name')

    if request.method == 'POST':
        customer_name = request.POST.get('customer_name', '').strip()
        customer_email = request.POST.get('customer_email', '').strip()
        customer_phone = request.POST.get('customer_phone', '').strip()
        notes = request.POST.get('notes', '').strip()
        due_date = request.POST.get('due_date') or None
        payment_method = request.POST.get('payment_method', '')
        payment_plan = request.POST.get('payment_plan', 'one_time')
        if payment_plan not in ('one_time', 'installment'):
            payment_plan = 'one_time'

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
            payment_plan=payment_plan,
            amount_paid=0.0,
            inventory_deducted=False,
            invoice_number=_generate_invoice_number(organization),
            status='pending',
        )

        total = 0.0
        valid_items_count = 0
        item_descriptions = []
        for inv_id, qty in zip(inventory_ids, quantities):
            try:
                inventory = Inventory.objects.get(
                    id=inv_id,
                    branch=branch,
                    organization=organization,
                    product__branch=branch,
                    product__organization=organization,
                )
                qty_int = int(qty) if qty else 0
                if qty_int <= 0:
                    continue
                if qty_int > inventory.quantity:
                    messages.error(
                        request,
                        f'Insufficient stock for {inventory.product.product_name}. Available: {inventory.quantity}.',
                    )
                    invoice.delete()
                    return render(request, 'ims/create_invoice.html', {
                        'branch': branch,
                        'inventory': inventory_qs,
                    })
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
                valid_items_count += 1
                item_descriptions.append(f"{inventory.product.product_name} (x{qty_int})")
            except Inventory.DoesNotExist:
                continue

        if valid_items_count == 0:
            invoice.delete()
            messages.error(request, 'Please add at least one valid product from this branch.')
            return render(request, 'ims/create_invoice.html', {
                'branch': branch,
                'inventory': inventory_qs,
            })

        invoice.total_amount = total
        invoice.save()

        currency = organization.currency_symbol if organization else '₦'
        actor = _user_display_With_role(request.user, organization)
        plan_label = invoice.get_payment_plan_display()
        _record_invoice_log(
            invoice=invoice,
            user=request.user,
            action='created',
            summary=(
                f"Created by {actor}. Payment plan: {plan_label}. "
                f"Total: {currency}{total:,.2f}. Items: {', '.join(item_descriptions)}."
            ),
        )

        messages.success(request, f'Invoice {invoice.invoice_number} created successfully.')
        return redirect('invoice_detail', pk=invoice.id)

    context = {
        'branch': branch,
        'inventory': inventory_qs,
    }
    return render(request, 'ims/create_invoice.html', context)


@role_required(roles=['owner', 'manager'])
@login_required
def invoice_detail(request, pk):
    """View a single invoice with all its items, payment history, and owner edit logs"""
    organization = get_request_organization(request)
    invoice = get_object_or_404(Invoice, id=pk, organization=organization)

    if not _check_branch_access(request, organization, invoice.branch):
        user_branch = get_request_branch(request, organization)
        if user_branch:
            return redirect('invoices', pk=user_branch.id)
        return redirect('dashboard')

    items = invoice.items.select_related('inventory__product').all()
    payments = invoice.payments.select_related('recorded_by').order_by('date_paid')
    org_role = get_request_org_role(request, organization)
    edit_logs = invoice.edit_logs.select_related('user').order_by('-timestamp') if org_role == 'owner' else []

    context = {
        'invoice': invoice,
        'items': items,
        'payments': payments,
        'edit_logs': edit_logs,
        'branch': invoice.branch,
    }
    return render(request, 'ims/invoice_detail.html', context)


@role_required(roles=['owner', 'manager'])
@login_required
def invoice_pdf(request, pk):
    """Download invoice as PDF"""
    organization = get_request_organization(request)
    invoice = get_object_or_404(Invoice, id=pk, organization=organization)

    if not _check_branch_access(request, organization, invoice.branch):
        user_branch = get_request_branch(request, organization)
        if user_branch:
            return redirect('invoices', pk=user_branch.id)
        return redirect('dashboard')

    items = invoice.items.select_related('inventory__product').all()
    payments = invoice.payments.select_related('recorded_by').order_by('date_paid')

    template_path = 'ims/invoice_pdf.html'
    context = {
        'invoice': invoice,
        'items': items,
        'payments': payments,
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


@role_required(roles=['owner', 'manager'])
@login_required
def confirm_payment(request, pk):
    """
    Record a full or installment payment on a pending or partially_paid invoice.
    - Inventory is deducted on the FIRST payment (when inventory_deducted is False).
    - Invoice remains 'partially_paid' (Not Completed) while balance_due > 0.
    - When balance_due reaches 0, invoice is marked 'paid' and a completed Sale record is created.
    """
    organization = get_request_organization(request)
    invoice = get_object_or_404(Invoice, id=pk, organization=organization)

    if not _check_branch_access(request, organization, invoice.branch):
        return redirect('invoice_detail', pk=invoice.id)

    if invoice.status not in ('pending', 'partially_paid'):
        messages.error(request, 'Only pending or partially paid invoices can receive payments.')
        return redirect('invoice_detail', pk=invoice.id)

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method') or invoice.payment_method or 'Cash'
        payment_notes = request.POST.get('payment_notes', '').strip()
        raw_amount = request.POST.get('amount_paid', '').strip()

        remaining_before = invoice.balance_due
        if raw_amount:
            try:
                amount_now = round(float(raw_amount), 2)
            except ValueError:
                messages.error(request, 'Please enter a valid payment amount.')
                return redirect('invoice_detail', pk=invoice.id)
        else:
            amount_now = remaining_before

        if amount_now <= 0:
            messages.error(request, 'Payment amount must be greater than zero.')
            return redirect('invoice_detail', pk=invoice.id)

        if amount_now > remaining_before + 0.01:
            currency = organization.currency_symbol if organization else '₦'
            messages.error(
                request,
                f'Payment amount ({currency}{amount_now:,.2f}) cannot exceed the remaining balance ({currency}{remaining_before:,.2f}).'
            )
            return redirect('invoice_detail', pk=invoice.id)

        # Cap minor floating point rounding to exact remaining balance
        if abs(amount_now - remaining_before) <= 0.01:
            amount_now = remaining_before

        currency = organization.currency_symbol if organization else '₦'
        actor = _user_display_With_role(request.user, organization)

        try:
            with transaction.atomic():
                items = list(invoice.items.select_related('inventory', 'inventory__product').all())
                deducted_this_time = False

                # Deduct inventory on the FIRST payment (first installment or full one-time payment)
                if not invoice.inventory_deducted:
                    for item in items:
                        if item.inventory and item.quantity:
                            inv = Inventory.objects.select_for_update().get(id=item.inventory.id)
                            if (inv.quantity or 0) < item.quantity:
                                raise ValueError(
                                    f"Insufficient stock for {inv.product.product_name}. "
                                    f"Available: {inv.quantity}, Required: {item.quantity}."
                                )
                            inv.quantity = (inv.quantity or 0) - item.quantity
                            if inv.quantity_available is not None and inv.quantity_available > 0:
                                inv.quantity_available = max(0, inv.quantity_available - item.quantity)
                            if inv.quantity <= 0:
                                inv.status = 'Restocking'
                            inv.save()
                    invoice.inventory_deducted = True
                    deducted_this_time = True

                # Record the installment payment entry
                InvoicePayment.objects.create(
                    invoice=invoice,
                    organization=organization,
                    branch=invoice.branch,
                    amount=amount_now,
                    payment_method=payment_method,
                    recorded_by=request.user,
                    notes=payment_notes or None,
                )

                invoice.amount_paid = round(float(invoice.amount_paid or 0.0) + amount_now, 2)
                invoice.payment_method = payment_method

                remaining_after = invoice.balance_due
                if remaining_after <= 0:
                    invoice.status = 'paid'
                    invoice.save()
                    _create_completed_sale_for_invoice(invoice, payment_method)

                    stock_note = " Inventory deducted." if deducted_this_time else ""
                    _record_invoice_log(
                        invoice=invoice,
                        user=request.user,
                        action='payment_recorded',
                        summary=(
                            f"Payment of {currency}{amount_now:,.2f} ({payment_method}) recorded by {actor}. "
                            f"Payment is now completed in full ({currency}{invoice.total_amount:,.2f}).{stock_note}"
                        ),
                    )
                else:
                    invoice.status = 'partially_paid'
                    if invoice.payment_plan != 'installment':
                        invoice.payment_plan = 'installment'
                    invoice.save()

                    stock_note = " Inventory deducted upon this first installment." if deducted_this_time else ""
                    _record_invoice_log(
                        invoice=invoice,
                        user=request.user,
                        action='payment_recorded',
                        summary=(
                            f"Installment payment of {currency}{amount_now:,.2f} ({payment_method}) recorded by {actor}. "
                            f"Total paid so far: {currency}{invoice.amount_paid:,.2f}. "
                            f"Remaining balance: {currency}{remaining_after:,.2f} (Not Completed).{stock_note}"
                        ),
                    )

            # Notify owner if another user recorded the payment
            owner = organization.owned_by
            if owner and owner != request.user:
                if invoice.status == 'paid':
                    notif_msg = (
                        f"Invoice {invoice.invoice_number} payment completed ({currency}{amount_now:,.2f} received, "
                        f"Total {currency}{invoice.total_amount:,.2f}) by {actor}."
                    )
                else:
                    notif_msg = (
                        f"Installment of {currency}{amount_now:,.2f} recorded for Invoice {invoice.invoice_number} "
                        f"by {actor}. Balance due: {currency}{invoice.balance_due:,.2f}."
                    )
                Notification.objects.create(
                    user=owner,
                    message=notif_msg[:500],
                    notification_type='success',
                    organization=organization,
                    is_read=False,
                )

            if invoice.status == 'paid':
                messages.success(
                    request,
                    f'Payment of {currency}{amount_now:,.2f} confirmed. Invoice {invoice.invoice_number} is now fully Paid!'
                )
            else:
                messages.success(
                    request,
                    f'Installment of {currency}{amount_now:,.2f} recorded for {invoice.invoice_number}. '
                    f'Remaining balance: {currency}{invoice.balance_due:,.2f} (Not Completed).'
                )
            return redirect('invoice_detail', pk=invoice.id)

        except ValueError as ve:
            messages.error(request, str(ve))
            return redirect('invoice_detail', pk=invoice.id)
        except Exception as e:
            import traceback
            print(f"ERROR in confirm_payment: {str(e)}")
            print(traceback.format_exc())
            messages.error(request, f'Error recording payment: {str(e)}')
            return redirect('invoice_detail', pk=invoice.id)

    return redirect('invoice_detail', pk=invoice.id)


@role_required(roles=['owner', 'manager'])
@login_required
def close_invoice(request, pk):
    """Close an unpaid pending invoice without confirming payment (no inventory change)"""
    organization = get_request_organization(request)
    invoice = get_object_or_404(Invoice, id=pk, organization=organization)

    if not _check_branch_access(request, organization, invoice.branch):
        return redirect('invoice_detail', pk=invoice.id)

    if invoice.status != 'pending' or (invoice.amount_paid or 0) > 0:
        messages.error(request, 'Only unpaid pending invoices can be closed.')
        return redirect('invoice_detail', pk=invoice.id)

    if request.method == 'POST':
        invoice.status = 'closed'
        invoice.save()
        actor = _user_display_With_role(request.user, organization)
        _record_invoice_log(
            invoice=invoice,
            user=request.user,
            action='closed',
            summary=f"Invoice closed by {actor}.",
        )
        messages.success(request, f'Invoice {invoice.invoice_number} has been closed.')
        return redirect('invoices', pk=invoice.branch.id)

    return redirect('invoice_detail', pk=invoice.id)


@role_required(roles=['owner'])
@login_required
def reopen_invoice(request, pk):
    """Reopen a closed invoice so it can be edited or paid (Owner only)"""
    organization = get_request_organization(request)
    invoice = get_object_or_404(Invoice, id=pk, organization=organization)

    if invoice.status != 'closed':
        messages.error(request, 'Only closed invoices can be reopened.')
        return redirect('invoice_detail', pk=invoice.id)

    if request.method == 'POST':
        invoice.status = 'partially_paid' if (invoice.amount_paid or 0) > 0 else 'pending'
        invoice.save(update_fields=['status'])
        actor = _user_display_With_role(request.user, organization)
        _record_invoice_log(
            invoice=invoice,
            user=request.user,
            action='reopened',
            summary=f"Invoice reopened by {actor} (status set to {invoice.get_status_display()}).",
        )
        messages.success(request, f'Invoice {invoice.invoice_number} has been reopened.')
        return redirect('invoice_detail', pk=invoice.id)

    return redirect('invoice_detail', pk=invoice.id)


@role_required(roles=['owner'])
@login_required
def delete_invoice(request, pk):
    """Delete a pending, closed, or partially paid invoice (Owner only)"""
    organization = get_request_organization(request)
    invoice = get_object_or_404(Invoice, id=pk, organization=organization)

    if invoice.status == 'paid':
        messages.error(request, 'Paid invoices cannot be deleted.')
        return redirect('invoice_detail', pk=invoice.id)

    if request.method == 'POST':
        branch_id = invoice.branch.id
        inv_num = invoice.invoice_number
        with transaction.atomic():
            # If inventory was already deducted on a partially paid invoice, restore it before deleting
            if invoice.inventory_deducted:
                for item in invoice.items.select_related('inventory').all():
                    if item.inventory and item.quantity:
                        inv = Inventory.objects.select_for_update().get(id=item.inventory.id)
                        inv.quantity = (inv.quantity or 0) + item.quantity
                        if inv.quantity > 0 and inv.status == 'Restocking':
                            inv.status = 'Available'
                        inv.save()
            ActivityLog.objects.create(
                organization=organization,
                branch=invoice.branch,
                staff=request.user,
                activity=f"Deleted invoice {inv_num} (Customer: {invoice.customer_name or 'N/A'})",
            )
            invoice.delete()
        messages.success(request, f'Invoice {inv_num} deleted.')
        return redirect('invoices', pk=branch_id)

    return redirect('invoice_detail', pk=invoice.id)


@role_required(roles=['owner', 'manager'])
@login_required
def edit_invoice(request, pk):
    """Edit a non-paid invoice (Owner & Manager) and log all changes for the Owner."""
    organization = get_request_organization(request)
    invoice = get_object_or_404(Invoice, id=pk, organization=organization)

    if not _check_branch_access(request, organization, invoice.branch):
        return redirect('invoice_detail', pk=invoice.id)

    if invoice.status in ('paid', 'closed'):
        if invoice.status == 'closed':
            messages.error(request, 'Closed invoices cannot be edited. The owner must reopen the invoice first.')
        else:
            messages.error(request, 'Paid invoices cannot be edited.')
        return redirect('invoice_detail', pk=invoice.id)

    branch = invoice.branch
    inventory_qs = Inventory.objects.filter(
        branch=branch,
        organization=organization,
        product__branch=branch,
        product__organization=organization,
    ).select_related('product').order_by('product__product_name')

    if request.method == 'POST':
        customer_name = request.POST.get('customer_name', '').strip() or None
        customer_email = request.POST.get('customer_email', '').strip() or None
        customer_phone = request.POST.get('customer_phone', '').strip() or None
        notes = request.POST.get('notes', '').strip() or None
        due_date_str = request.POST.get('due_date', '').strip() or None
        payment_method = request.POST.get('payment_method', '').strip() or None
        payment_plan = request.POST.get('payment_plan', invoice.payment_plan or 'one_time')
        if payment_plan not in ('one_time', 'installment'):
            payment_plan = 'one_time'

        inventory_ids = request.POST.getlist('inventory_id[]')
        quantities = request.POST.getlist('quantity[]')

        if not inventory_ids or not any(quantities):
            messages.error(request, 'Please add at least one item to the invoice.')
            return redirect('edit_invoice', pk=invoice.id)

        # Snapshot existing state for diff logging & inventory reconciliation
        old_customer_name = invoice.customer_name
        old_customer_email = invoice.customer_email
        old_customer_phone = invoice.customer_phone
        old_due_date = str(invoice.due_date) if invoice.due_date else None
        old_payment_method = invoice.payment_method
        old_payment_plan = invoice.payment_plan
        old_notes = invoice.notes
        old_total = float(invoice.total_amount or 0.0)

        old_items_qs = list(invoice.items.select_related('inventory__product').all())
        old_items_summary = [
            f"{it.inventory.product.product_name if it.inventory and it.inventory.product else 'Item'} (x{it.quantity})"
            for it in old_items_qs
        ]
        old_qty_by_inv = {}
        for it in old_items_qs:
            if it.inventory_id:
                key = str(it.inventory_id)
                old_qty_by_inv[key] = old_qty_by_inv.get(key, 0) + (it.quantity or 0)

        # Parse & aggregate new requested items
        parsed_new_items = []
        new_qty_by_inv = {}
        for inv_id, qty in zip(inventory_ids, quantities):
            try:
                inv = Inventory.objects.select_related('product').get(
                    id=inv_id, branch=branch, organization=organization
                )
                qty_int = int(qty) if qty else 0
                if qty_int <= 0:
                    continue
                parsed_new_items.append((inv, qty_int))
                key = str(inv.id)
                new_qty_by_inv[key] = new_qty_by_inv.get(key, 0) + qty_int
            except (Inventory.DoesNotExist, ValueError):
                continue

        if not parsed_new_items:
            messages.error(request, 'Please add at least one valid product.')
            return redirect('edit_invoice', pk=invoice.id)

        new_total = sum((inv.sale_price or 0.0) * qty_int for inv, qty_int in parsed_new_items)
        currency = organization.currency_symbol if organization else '₦'

        if float(invoice.amount_paid or 0.0) > new_total + 0.01:
            messages.error(
                request,
                f'Updated invoice total ({currency}{new_total:,.2f}) cannot be less than the amount already paid ({currency}{invoice.amount_paid:,.2f}).'
            )
            return redirect('edit_invoice', pk=invoice.id)

        try:
            with transaction.atomic():
                # Validate stock (accounting for already-deducted quantities if inventory_deducted is True)
                for inv_id_str, requested_qty in new_qty_by_inv.items():
                    inv = Inventory.objects.select_for_update().select_related('product').get(
                        id=inv_id_str, branch=branch, organization=organization
                    )
                    already_reserved = old_qty_by_inv.get(inv_id_str, 0) if invoice.inventory_deducted else 0
                    effective_available = (inv.quantity or 0) + already_reserved
                    if requested_qty > effective_available:
                        raise ValueError(
                            f'Insufficient stock for {inv.product.product_name}. Available: {effective_available}.'
                        )

                # If inventory was already deducted (e.g. after first installment), reconcile stock changes
                if invoice.inventory_deducted:
                    all_inv_ids = set(old_qty_by_inv.keys()) | set(new_qty_by_inv.keys())
                    for inv_id_str in all_inv_ids:
                        diff = new_qty_by_inv.get(inv_id_str, 0) - old_qty_by_inv.get(inv_id_str, 0)
                        if diff != 0:
                            inv = Inventory.objects.select_for_update().get(
                                id=inv_id_str, branch=branch, organization=organization
                            )
                            inv.quantity = max(0, (inv.quantity or 0) - diff)
                            if inv.quantity <= 0:
                                inv.status = 'Restocking'
                            elif inv.status == 'Restocking':
                                inv.status = 'Available'
                            inv.save()

                # Update invoice header fields
                invoice.customer_name = customer_name
                invoice.customer_email = customer_email
                invoice.customer_phone = customer_phone
                invoice.notes = notes
                invoice.due_date = due_date_str
                invoice.payment_method = payment_method
                invoice.payment_plan = payment_plan
                invoice.total_amount = new_total

                # Replace all line items
                invoice.items.all().delete()
                new_items_summary = []
                for inv, qty_int in parsed_new_items:
                    unit_price = inv.sale_price or 0.0
                    item_total = unit_price * qty_int
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        organization=organization,
                        branch=branch,
                        inventory=inv,
                        quantity=qty_int,
                        unit_price=unit_price,
                        total=item_total,
                    )
                    new_items_summary.append(f"{inv.product.product_name} (x{qty_int})")

                # Re-evaluate payment status if payments were already made
                if float(invoice.amount_paid or 0.0) > 0:
                    if invoice.balance_due <= 0:
                        invoice.status = 'paid'
                        invoice.save()
                        _create_completed_sale_for_invoice(invoice, invoice.payment_method)
                    else:
                        invoice.status = 'partially_paid'
                        invoice.save()
                else:
                    invoice.save()

                # Build detailed edit summary for the Owner
                changes = []
                if old_customer_name != customer_name:
                    changes.append(f"Customer name: '{old_customer_name or '—'}' → '{customer_name or '—'}'")
                if old_customer_email != customer_email:
                    changes.append(f"Customer email: '{old_customer_email or '—'}' → '{customer_email or '—'}'")
                if old_customer_phone != customer_phone:
                    changes.append(f"Customer phone: '{old_customer_phone or '—'}' → '{customer_phone or '—'}'")
                if old_due_date != due_date_str:
                    changes.append(f"Due date: '{old_due_date or '—'}' → '{due_date_str or '—'}'")
                if old_payment_plan != payment_plan:
                    changes.append(f"Payment plan: '{old_payment_plan}' → '{payment_plan}'")
                if old_payment_method != payment_method:
                    changes.append(f"Payment method: '{old_payment_method or '—'}' → '{payment_method or '—'}'")
                if old_notes != notes:
                    changes.append("Updated notes")
                if old_items_summary != new_items_summary:
                    changes.append(f"Items: [{', '.join(old_items_summary)}] → [{', '.join(new_items_summary)}]")
                if round(old_total, 2) != round(new_total, 2):
                    changes.append(f"Total: {currency}{old_total:,.2f} → {currency}{new_total:,.2f}")

                actor = _user_display_With_role(request.user, organization)
                change_text = "; ".join(changes) if changes else "Saved invoice without field changes"
                _record_invoice_log(
                    invoice=invoice,
                    user=request.user,
                    action='edited',
                    summary=f"Edited by {actor}: {change_text}.",
                )

                # Notify owner if a manager edited the invoice
                owner = organization.owned_by
                if owner and owner != request.user:
                    Notification.objects.create(
                        user=owner,
                        message=f"Invoice {invoice.invoice_number} was edited by {actor}.",
                        notification_type='info',
                        organization=organization,
                        is_read=False,
                    )

            messages.success(request, f'Invoice {invoice.invoice_number} updated successfully.')
            return redirect('invoice_detail', pk=invoice.id)

        except ValueError as ve:
            messages.error(request, str(ve))
            return redirect('edit_invoice', pk=invoice.id)

    existing_items = invoice.items.select_related('inventory__product').all()
    context = {
        'invoice': invoice,
        'branch': branch,
        'inventory': inventory_qs,
        'existing_items': existing_items,
    }
    return render(request, 'ims/edit_invoice.html', context)
