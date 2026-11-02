import io
import json
import logging
from datetime import date, datetime
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template, render_to_string
from django.urls import reverse
from django.utils import timezone
from xhtml2pdf import pisa

from account.decorators import role_required
from account.models import ActivityLog, Branch, Notification
from account.utils import get_request_org_role, get_request_organization
from ims.models import Inventory, Product, RestockRequest, RestockRequestItem

logger = logging.getLogger(__name__)


def _generate_restock_number(organization):
    """Generate a unique restock request number like RST-20261102-0001"""
    today = date.today().strftime('%Y%m%d')
    count = RestockRequest.objects.filter(
        organization=organization,
        date_created__date=date.today()
    ).count() + 1
    return f"RST-{today}-{count:04d}"


def _check_branch_access(request, organization, branch):
    """
    Ensure that a manager can only access restock requests for their assigned branch.
    Owners have access to all branches in their organization.
    """
    role = get_request_org_role(request, organization)
    if role == 'owner':
        return True
    if role == 'manager':
        assigned_branch = request.user.get_branch_in_organization(organization) or getattr(request.user, 'branch', None)
        if assigned_branch and str(assigned_branch.id) != str(branch.id):
            messages.error(request, 'You only have permission to manage restock requests for your assigned branch.')
            return False
        return True
    return False


def _clean_email_list(raw_emails):
    """
    Accepts a list of strings (each possibly comma/semicolon-separated) and returns
    a deduplicated list of non-empty trimmed email addresses.
    """
    cleaned = []
    seen = set()
    for entry in raw_emails:
        if not entry:
            continue
        for part in str(entry).replace(';', ',').split(','):
            addr = part.strip()
            if addr and '@' in addr and addr.lower() not in seen:
                seen.add(addr.lower())
                cleaned.append(addr)
    return cleaned


def _render_restock_pdf_bytes(restock_request):
    """Render the RestockRequest into PDF bytes using xhtml2pdf."""
    items = restock_request.items.select_related('inventory__product', 'inventory__product__category').all()
    template = get_template('ims/restock_request_pdf.html')
    html = template.render({
        'restock_request': restock_request,
        'items': items,
        'organization': restock_request.organization,
        'branch': restock_request.branch,
    })
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
    if pisa_status.err:
        logger.error("Failed to generate PDF for restock request %s", restock_request.request_number)
        return None
    return pdf_buffer.getvalue()


def _send_restock_request_email(request, restock_request):
    """
    Send the restock request email with the attached PDF and downloadable PDF link
    to all vendor POC emails configured on the request.
    """
    recipients = restock_request.email_list
    if not recipients:
        return False, "No vendor POC email addresses provided."

    pdf_bytes = _render_restock_pdf_bytes(restock_request)
    pdf_path = reverse('restock_request_pdf', kwargs={'pk': restock_request.id})
    pdf_url = request.build_absolute_uri(pdf_path)
    quote_path = reverse('supplier_restock_quote', kwargs={'pk': restock_request.id})
    quote_url = request.build_absolute_uri(quote_path)

    org = restock_request.organization
    branch = restock_request.branch
    org_name = org.name if org else "Quicksales Store"
    branch_name = branch.name if branch else "Main Branch"
    items = list(restock_request.items.select_related('inventory__product', 'inventory__product__category').all())

    context = {
        'restock_request': restock_request,
        'organization': org,
        'org_name': org_name,
        'branch': branch,
        'branch_name': branch_name,
        'items': items,
        'pdf_url': pdf_url,
        'quote_url': quote_url,
        'requested_by': restock_request.requested_by,
    }

    subject = f"Restock Request #{restock_request.request_number} from {org_name} ({branch_name})"
    html_content = render_to_string('ims/emails/restock_request_email.html', context)
    text_lines = [
        f"Hello {restock_request.supplier_name or 'Supplier Partner'},",
        "",
        f"{org_name} ({branch_name}) has requested a product restock (Request #{restock_request.request_number}).",
        "",
        "Requested Products:",
    ]
    for idx, item in enumerate(items, start=1):
        unit_label = item.inventory.product.unit or "units"
        text_lines.append(f"  {idx}. {item.inventory.product.product_name} — Qty Needed: {item.quantity_requested} {unit_label}")
    if restock_request.expected_date:
        text_lines.append(f"\nExpected Delivery Date: {restock_request.expected_date}")
    if restock_request.notes:
        text_lines.append(f"\nNotes: {restock_request.notes}")
    text_lines.append(f"\nSubmit Your Cost Price Quote Online: {quote_url}")
    text_lines.append(f"Download Restock Request PDF: {pdf_url}")
    text_lines.append("\nA copy of the PDF is also attached to this email.")
    text_content = "\n".join(text_lines)

    from_email = f"{org_name} <{getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@quicksales.africa')}>"
    reply_email = None
    if restock_request.requested_by and restock_request.requested_by.email:
        reply_email = restock_request.requested_by.email
    elif org and getattr(org, 'owned_by', None) and org.owned_by.email:
        reply_email = org.owned_by.email

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=recipients,
            reply_to=[reply_email] if reply_email else None,
        )
        msg.attach_alternative(html_content, "text/html")
        if pdf_bytes:
            msg.attach(f"Restock_{restock_request.request_number}.pdf", pdf_bytes, "application/pdf")
        msg.send(fail_silently=False)

        restock_request.email_sent = True
        restock_request.save(update_fields=['email_sent', 'date_updated'])
        return True, f"Email with PDF sent to {', '.join(recipients)}."
    except Exception as exc:
        logger.exception("Error sending restock request email for %s: %s", restock_request.request_number, exc)
        return False, f"Restock request saved, but email could not be sent: {exc}"


@role_required(roles=['owner', 'manager'])
@login_required
def restock_requests(request, pk):
    """List all supplier restock requests for a branch."""
    organization = get_request_organization(request)
    branch = get_object_or_404(Branch, id=pk, organization=organization)
    if not _check_branch_access(request, organization, branch):
        return redirect('dashboard')

    qs = RestockRequest.objects.filter(
        organization=organization,
        branch=branch
    ).select_related('requested_by', 'branch').prefetch_related('items__inventory__product').order_by('-date_created')

    status_filter = request.GET.get('status', '').strip()
    search_query = request.GET.get('q', '').strip()

    if status_filter:
        qs = qs.filter(status=status_filter)
    if search_query:
        qs = (
            qs.filter(request_number__icontains=search_query)
            | qs.filter(supplier_name__icontains=search_query)
            | qs.filter(vendor_emails__icontains=search_query)
        )

    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'branch': branch,
        'restock_page': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'org_role': get_request_org_role(request, organization),
    }
    return render(request, 'ims/restock_requests.html', context)


@role_required(roles=['owner', 'manager'])
@login_required
def create_restock_request(request, pk):
    """
    Create a supplier restock request for branch `pk`.
    Supports:
    - Quick request from a single product modal on the Inventory page (`inventory_id` + `quantity_requested`)
    - Multi-product request from the Create Restock Request form (`items_json` or `inventory_id[]`)
    Vendor POC emails are completely optional (supports 0, 1, or multiple POC emails).
    """
    organization = get_request_organization(request)
    branch = get_object_or_404(Branch, id=pk, organization=organization)
    if not _check_branch_access(request, organization, branch):
        return redirect('dashboard')

    inventories = Inventory.objects.filter(
        organization=organization,
        branch=branch
    ).select_related('product', 'product__category').order_by('product__product_name')

    if request.method == 'POST':
        supplier_name = request.POST.get('supplier_name', '').strip()
        expected_date_str = request.POST.get('expected_date', '').strip()
        notes = request.POST.get('notes', '').strip()

        # Collect optional vendor POC emails (0, 1, or multiple)
        raw_emails = request.POST.getlist('vendor_email') + [request.POST.get('vendor_emails', '')]
        email_list = _clean_email_list(raw_emails)
        vendor_emails_str = ', '.join(email_list) if email_list else ''

        # Parse requested items (either from items_json or single/multiple inventory_id fields)
        parsed_items = []
        items_json = request.POST.get('items_json', '').strip()
        if items_json:
            try:
                raw_items = json.loads(items_json)
                for entry in raw_items:
                    inv_id = entry.get('inventory_id')
                    qty = int(entry.get('quantity', 0))
                    if inv_id and qty > 0:
                        parsed_items.append((inv_id, qty))
            except (ValueError, TypeError):
                messages.error(request, 'Invalid product list submitted.')
                return redirect('create_restock_request', pk=branch.id)
        else:
            inv_ids = request.POST.getlist('inventory_id')
            qtys = request.POST.getlist('quantity_requested')
            for inv_id, qty_str in zip(inv_ids, qtys):
                try:
                    qty = int(qty_str)
                except (ValueError, TypeError):
                    qty = 0
                if inv_id and qty > 0:
                    parsed_items.append((inv_id, qty))

        if not parsed_items:
            messages.error(request, 'Please select at least one product and enter a valid quantity to request.')
            return redirect(request.META.get('HTTP_REFERER') or reverse('inventorys', kwargs={'pk': branch.id}))

        expected_date_val = None
        if expected_date_str:
            try:
                expected_date_val = datetime.strptime(expected_date_str, '%Y-%m-%d').date()
            except ValueError:
                expected_date_val = None

        with transaction.atomic():
            restock_req = RestockRequest.objects.create(
                organization=organization,
                branch=branch,
                requested_by=request.user,
                request_number=_generate_restock_number(organization),
                supplier_name=supplier_name or None,
                vendor_emails=vendor_emails_str or None,
                expected_date=expected_date_val,
                notes=notes or None,
                status='pending',
            )

            created_count = 0
            for inv_id, qty in parsed_items:
                inv = Inventory.objects.select_related('product').filter(
                    id=inv_id,
                    organization=organization,
                    branch=branch
                ).first()
                if not inv:
                    continue
                RestockRequestItem.objects.create(
                    restock_request=restock_req,
                    organization=organization,
                    branch=branch,
                    inventory=inv,
                    quantity_requested=qty,
                    quantity_supplied=0,
                    is_supplied=False,
                    is_restocked=False,
                )
                created_count += 1

                # Remember optional POC emails on the product if provided
                if vendor_emails_str and inv.product:
                    inv.product.supplier_emails = vendor_emails_str
                    inv.product.save(update_fields=['supplier_emails'])

            if created_count == 0:
                restock_req.delete()
                messages.error(request, 'No valid branch products were found for this restock request.')
                return redirect('inventorys', pk=branch.id)

            ActivityLog.objects.create(
                organization=organization,
                branch=branch,
                staff=request.user,
                activity=f"Created Restock Request {restock_req.request_number} ({created_count} item(s))"
            )

        # Send email + PDF only if 1 or more vendor POC emails were entered
        if email_list:
            sent_ok, msg_text = _send_restock_request_email(request, restock_req)
            if sent_ok:
                messages.success(request, f"Restock Request {restock_req.request_number} created! {msg_text}")
            else:
                messages.warning(request, msg_text)
        else:
            messages.success(
                request,
                f"Restock Request {restock_req.request_number} created! You can download the PDF or send it to supplier emails anytime."
            )

        return redirect('restock_request_detail', pk=restock_req.id)

    context = {
        'branch': branch,
        'inventories': inventories,
        'org_role': get_request_org_role(request, organization),
    }
    return render(request, 'ims/create_restock_request.html', context)


@role_required(roles=['owner', 'manager'])
@login_required
def restock_request_detail(request, pk):
    """View a restock request, download its PDF, resend to POCs, or tick supplied items to restock directly."""
    organization = get_request_organization(request)
    restock_req = get_object_or_404(
        RestockRequest.objects.select_related('organization', 'branch', 'requested_by'),
        id=pk,
        organization=organization
    )
    if not _check_branch_access(request, organization, restock_req.branch):
        return redirect('dashboard')

    items = restock_req.items.select_related(
        'inventory', 'inventory__product', 'inventory__product__category', 'restocked_by', 'price_approved_by'
    ).all()

    unrestocked_count = sum(1 for item in items if not item.is_restocked)
    quote_url = request.build_absolute_uri(reverse('supplier_restock_quote', kwargs={'pk': restock_req.id}))

    context = {
        'restock_request': restock_req,
        'branch': restock_req.branch,
        'items': items,
        'unrestocked_count': unrestocked_count,
        'quote_url': quote_url,
        'org_role': get_request_org_role(request, organization),
    }
    return render(request, 'ims/restock_request_detail.html', context)


def restock_request_pdf(request, pk):
    """
    Generate and serve the downloadable PDF for a RestockRequest.
    Accessible via UUID link so external suppliers can download the PDF directly from their email.
    """
    restock_req = get_object_or_404(
        RestockRequest.objects.select_related('organization', 'branch', 'requested_by'),
        id=pk
    )
    pdf_bytes = _render_restock_pdf_bytes(restock_req)
    if pdf_bytes is None:
        return HttpResponse("Error generating Restock Request PDF", status=500)

    disposition = 'inline' if request.GET.get('inline') == '1' else 'attachment'
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'{disposition}; filename="Restock_{restock_req.request_number}.pdf"'
    return response


@role_required(roles=['owner', 'manager'])
@login_required
def fulfill_restock_request(request, pk):
    """
    Tick supplied items on a RestockRequest and directly restock the branch's Inventory in one click.
    """
    if request.method != 'POST':
        return redirect('restock_request_detail', pk=pk)

    organization = get_request_organization(request)
    restock_req = get_object_or_404(
        RestockRequest.objects.select_related('organization', 'branch'),
        id=pk,
        organization=organization
    )
    if not _check_branch_access(request, organization, restock_req.branch):
        return redirect('dashboard')

    if restock_req.status == 'cancelled':
        messages.error(request, 'Cannot restock items from a cancelled restock request.')
        return redirect('restock_request_detail', pk=restock_req.id)

    ticked_ids = set(request.POST.getlist('item_ids'))
    if not ticked_ids:
        messages.warning(request, 'Please tick at least one supplied product to restock.')
        return redirect('restock_request_detail', pk=restock_req.id)

    restocked_names = []
    with transaction.atomic():
        items = list(restock_req.items.select_related('inventory', 'inventory__product').select_for_update())
        for item in items:
            if str(item.id) in ticked_ids and not item.is_restocked:
                raw_qty = request.POST.get(f'quantity_supplied_{item.id}', item.default_supply_quantity)
                try:
                    qty_supplied = int(raw_qty)
                except (ValueError, TypeError):
                    qty_supplied = item.default_supply_quantity

                if qty_supplied <= 0:
                    continue

                inv = Inventory.objects.select_for_update().select_related('product').get(id=item.inventory.id)
                inv.quantity = (inv.quantity or 0) + qty_supplied
                inv.quantity_restocked = qty_supplied
                inv.status = 'Available'

                # Apply Owner-approved cost price and new sale price automatically upon delivery/restock
                price_updated_note = ""
                if item.price_status == 'accepted':
                    if item.approved_cost_price is not None:
                        inv.cost_price = item.approved_cost_price
                    if item.new_sale_price is not None:
                        inv.sale_price = item.new_sale_price
                    if inv.product and inv.cost_price is not None and inv.sale_price is not None:
                        inv.product.profit = float(inv.sale_price) - float(inv.cost_price)
                        inv.product.save(update_fields=['profit'])
                    price_updated_note = f" [Cost: {inv.cost_price}, Sale: {inv.sale_price}]"

                inv.save()
                # Reset quantity_restocked to 0 after historical record save, matching standard restock behavior
                Inventory.objects.filter(id=inv.id).update(quantity_restocked=0)

                item.quantity_supplied = qty_supplied
                item.is_supplied = True
                item.is_restocked = True
                item.restocked_at = timezone.now()
                item.restocked_by = request.user
                item.save()

                restocked_names.append(f"{inv.product.product_name} (+{qty_supplied}){price_updated_note}")

        # Re-evaluate overall request status
        all_items = list(restock_req.items.all())
        if all_items and all(i.is_restocked for i in all_items):
            restock_req.status = 'completed'
        elif any(i.is_restocked for i in all_items):
            restock_req.status = 'partially_supplied'
        restock_req.save(update_fields=['status', 'date_updated'])

        if restocked_names:
            summary_str = ", ".join(restocked_names)
            ActivityLog.objects.create(
                organization=organization,
                branch=restock_req.branch,
                staff=request.user,
                activity=f"[Restock {restock_req.request_number}] Restocked supplied items: {summary_str}"[:1000],
            )
            if organization.owned_by and organization.owned_by != request.user:
                Notification.objects.create(
                    organization=organization,
                    user=organization.owned_by,
                    message=f"{request.user.first_name or request.user.email} restocked supplied items for {restock_req.request_number} in {restock_req.branch.name}: {summary_str}"[:255],
                )

    # Invalidate inventory cache if applicable
    try:
        for key_pattern in cache.keys(f"inventory_list:org:{organization.id}:*"):
            cache.delete(key_pattern)
    except Exception:
        pass

    if restocked_names:
        messages.success(
            request,
            f"Successfully restocked {len(restocked_names)} item(s) into {restock_req.branch.name} inventory: {', '.join(restocked_names)}."
        )
    else:
        messages.info(request, "No new items were restocked.")

    return redirect('restock_request_detail', pk=restock_req.id)


@role_required(roles=['owner', 'manager'])
@login_required
def resend_restock_email(request, pk):
    """Update optional vendor POC emails on an existing RestockRequest and send/resend the PDF email."""
    if request.method != 'POST':
        return redirect('restock_request_detail', pk=pk)

    organization = get_request_organization(request)
    restock_req = get_object_or_404(
        RestockRequest.objects.select_related('organization', 'branch', 'requested_by'),
        id=pk,
        organization=organization
    )
    if not _check_branch_access(request, organization, restock_req.branch):
        return redirect('dashboard')

    raw_emails = request.POST.getlist('vendor_email') + [request.POST.get('vendor_emails', '')]
    email_list = _clean_email_list(raw_emails)
    if email_list:
        restock_req.vendor_emails = ', '.join(email_list)
        restock_req.save(update_fields=['vendor_emails', 'date_updated'])

    if not restock_req.email_list:
        messages.warning(request, 'Please enter at least one vendor POC email address to send the email.')
        return redirect('restock_request_detail', pk=restock_req.id)

    sent_ok, msg_text = _send_restock_request_email(request, restock_req)
    if sent_ok:
        messages.success(request, msg_text)
    else:
        messages.error(request, msg_text)
    return redirect('restock_request_detail', pk=restock_req.id)


@role_required(roles=['owner', 'manager'])
@login_required
def cancel_restock_request(request, pk):
    """Cancel a pending restock request if no items have been restocked yet."""
    if request.method != 'POST':
        return redirect('restock_request_detail', pk=pk)

    organization = get_request_organization(request)
    restock_req = get_object_or_404(
        RestockRequest.objects.select_related('organization', 'branch'),
        id=pk,
        organization=organization
    )
    if not _check_branch_access(request, organization, restock_req.branch):
        return redirect('dashboard')

    if restock_req.items.filter(is_restocked=True).exists():
        messages.error(request, 'Cannot cancel a restock request that already has restocked items.')
        return redirect('restock_request_detail', pk=restock_req.id)

    restock_req.status = 'cancelled'
    restock_req.save(update_fields=['status', 'date_updated'])
    messages.success(request, f"Restock Request {restock_req.request_number} has been cancelled.")
    return redirect('restock_request_detail', pk=restock_req.id)


def supplier_restock_quote(request, pk):
    """
    Public supplier portal (accessible via unique UUID link from email or WhatsApp)
    where the vendor can enter the unit cost price and available quantity for each requested item.
    Never exposes current merchant cost prices, sale prices, or stock levels.
    """
    restock_req = get_object_or_404(
        RestockRequest.objects.select_related('organization', 'branch', 'requested_by'),
        id=pk
    )
    items = list(restock_req.items.select_related('inventory__product', 'inventory__product__category').all())
    is_locked = restock_req.status in ('completed', 'cancelled')
    submitted_success = request.GET.get('submitted') == '1'

    if request.method == 'POST' and not is_locked:
        submitted_by_name = request.POST.get('quote_submitted_by_name', '').strip()
        submitted_by_email = request.POST.get('quote_submitted_by_email', '').strip()
        supplier_notes = request.POST.get('supplier_quote_notes', '').strip()

        updated_items = 0
        now = timezone.now()
        with transaction.atomic():
            for item in items:
                if item.is_restocked:
                    continue
                raw_cost = request.POST.get(f'quoted_cost_price_{item.id}', '').strip()
                raw_qty = request.POST.get(f'quoted_quantity_{item.id}', '').strip()

                cost_val = None
                if raw_cost != '':
                    try:
                        parsed_cost = float(raw_cost)
                        if parsed_cost >= 0:
                            cost_val = round(parsed_cost, 2)
                    except (ValueError, TypeError):
                        cost_val = None

                qty_val = item.quantity_requested
                if raw_qty != '':
                    try:
                        parsed_qty = int(raw_qty)
                        if parsed_qty >= 0:
                            qty_val = parsed_qty
                    except (ValueError, TypeError):
                        qty_val = item.quantity_requested

                if cost_val is not None:
                    item.quoted_cost_price = cost_val
                    item.quoted_quantity = qty_val
                    item.quoted_at = now
                    item.price_status = 'quoted'
                    item.save(update_fields=[
                        'quoted_cost_price', 'quoted_quantity', 'quoted_at', 'price_status'
                    ])
                    updated_items += 1

            if updated_items > 0:
                restock_req.quote_submitted = True
                restock_req.quote_submitted_at = now
                if submitted_by_name:
                    restock_req.quote_submitted_by_name = submitted_by_name
                if submitted_by_email:
                    restock_req.quote_submitted_by_email = submitted_by_email
                if supplier_notes:
                    restock_req.supplier_quote_notes = supplier_notes
                restock_req.save(update_fields=[
                    'quote_submitted', 'quote_submitted_at',
                    'quote_submitted_by_name', 'quote_submitted_by_email',
                    'supplier_quote_notes', 'date_updated'
                ])

                org = restock_req.organization
                who_str = submitted_by_email or submitted_by_name or restock_req.supplier_name or "Supplier"
                if org and org.owned_by:
                    Notification.objects.create(
                        organization=org,
                        user=org.owned_by,
                        message=(
                            f"Supplier ({who_str}) submitted cost prices for Restock Request "
                            f"{restock_req.request_number} ({restock_req.branch.name}). "
                            f"Review to accept and set new sale prices."
                        )[:255]
                    )

        return redirect(f"{reverse('supplier_restock_quote', kwargs={'pk': restock_req.id})}?submitted=1")

    context = {
        'restock_request': restock_req,
        'organization': restock_req.organization,
        'branch': restock_req.branch,
        'items': items,
        'is_locked': is_locked,
        'submitted_success': submitted_success,
    }
    return render(request, 'ims/supplier_restock_quote.html', context)


@role_required(roles=['owner'])
@login_required
def approve_restock_item_prices(request, pk):
    """
    Owner-only view to accept the supplier's cost price and set the new sale price
    for one or all items on a RestockRequest.
    The approved cost price and new sale price are stored on the RestockRequestItem and
    automatically applied to the branch Inventory as soon as the item is restocked (or
    immediately if the item was already restocked).
    """
    if request.method != 'POST':
        return redirect('restock_request_detail', pk=pk)

    organization = get_request_organization(request)
    restock_req = get_object_or_404(
        RestockRequest.objects.select_related('organization', 'branch'),
        id=pk,
        organization=organization
    )

    target_item_id = request.POST.get('single_item_id', '').strip()
    items_qs = restock_req.items.select_related('inventory', 'inventory__product').all()
    if target_item_id:
        items_qs = items_qs.filter(id=target_item_id)

    approved_count = 0
    applied_immediately_count = 0
    now = timezone.now()

    with transaction.atomic():
        for item in items_qs:
            raw_cost = request.POST.get(f'approved_cost_price_{item.id}', '').strip()
            raw_sale = request.POST.get(f'new_sale_price_{item.id}', '').strip()

            if raw_cost == '' and item.quoted_cost_price is not None:
                cost_val = float(item.quoted_cost_price)
            elif raw_cost != '':
                try:
                    cost_val = round(float(raw_cost), 2)
                except (ValueError, TypeError):
                    cost_val = None
            else:
                cost_val = None

            if raw_sale == '' and item.inventory.sale_price is not None:
                sale_val = float(item.inventory.sale_price)
            elif raw_sale != '':
                try:
                    sale_val = round(float(raw_sale), 2)
                except (ValueError, TypeError):
                    sale_val = None
            else:
                sale_val = None

            if cost_val is None or sale_val is None:
                continue

            item.approved_cost_price = cost_val
            item.new_sale_price = sale_val
            item.price_status = 'accepted'
            item.price_approved_by = request.user
            item.price_approved_at = now
            item.save(update_fields=[
                'approved_cost_price', 'new_sale_price', 'price_status',
                'price_approved_by', 'price_approved_at'
            ])
            approved_count += 1

            # If this item was already restocked earlier, apply the approved prices to Inventory now
            if item.is_restocked:
                inv = Inventory.objects.select_for_update().select_related('product').get(id=item.inventory.id)
                inv.cost_price = cost_val
                inv.sale_price = sale_val
                inv.save()
                if inv.product:
                    inv.product.profit = float(sale_val) - float(cost_val)
                    inv.product.save(update_fields=['profit'])
                applied_immediately_count += 1

        if approved_count > 0:
            ActivityLog.objects.create(
                organization=organization,
                branch=restock_req.branch,
                staff=request.user,
                activity=(
                    f"[Restock {restock_req.request_number}] Owner approved cost & sale prices "
                    f"for {approved_count} item(s) (applied on restock)."
                )[:1000]
            )

    if approved_count > 0:
        if applied_immediately_count > 0:
            messages.success(
                request,
                f"Accepted cost & new sale price for {approved_count} item(s) and updated inventory prices."
            )
        else:
            messages.success(
                request,
                f"Accepted cost & new sale price for {approved_count} item(s). "
                f"The new cost and sale prices will automatically update on Inventory as soon as the items are restocked."
            )
    else:
        messages.warning(request, "Please enter a valid cost price and sale price to accept.")

    return redirect('restock_request_detail', pk=restock_req.id)


