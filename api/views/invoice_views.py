from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.template.loader import get_template
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from xhtml2pdf import pisa

from account.models import Notification
from api.context import resolve_mobile_context
from api.pagination import paginate_queryset
from api.permissions import (
    HasRoleOrFeaturePermission,
    IsOwnerOnly,
    MOBILE_DEFAULT_PERMISSIONS,
)
from api.serializers.invoice import (
    InvoiceCreateSerializer,
    InvoiceSerializer,
    InvoiceUpdateSerializer,
    RecordPaymentSerializer,
)
from ims.models import Inventory, Invoice, InvoiceItem, InvoicePayment
from ims.view.invoice_views import (
    _create_completed_sale_for_invoice,
    _generate_invoice_number,
    _record_invoice_log,
    _user_display_With_role,
)


def _get_scoped_invoice(request, ctx, pk):
    qs = (
        Invoice.objects.filter(id=pk, organization=ctx.organization)
        .select_related("branch", "created_by")
        .prefetch_related("items__inventory__product", "payments__recorded_by", "edit_logs__user")
    )
    if ctx.role != "owner":
        qs = qs.filter(branch=ctx.branch, created_by=request.user)
    return qs.first()


class MobileInvoiceListCreateView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner",)
    required_feature_permissions = ("invoices",)

    @extend_schema(tags=["Invoices"])
    def get(self, request):
        ctx = resolve_mobile_context(request)
        qs = (
            Invoice.objects.filter(organization=ctx.organization)
            .select_related("branch", "created_by")
            .prefetch_related("items__inventory__product", "payments__recorded_by", "edit_logs__user")
            .order_by("-date_created")
        )
        if ctx.branch:
            qs = qs.filter(branch=ctx.branch)
        if ctx.role != "owner":
            qs = qs.filter(created_by=request.user)
        else:
            staff_id = request.query_params.get("staff")
            if staff_id:
                qs = qs.filter(created_by_id=staff_id)

        inv_status = request.query_params.get("status")
        if inv_status:
            qs = qs.filter(status=inv_status)

        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(invoice_number__icontains=search)
                | Q(customer_name__icontains=search)
                | Q(customer_phone__icontains=search)
            )

        return paginate_queryset(request, qs, InvoiceSerializer)

    @extend_schema(request=InvoiceCreateSerializer, tags=["Invoices"])
    def post(self, request):
        ctx = resolve_mobile_context(request)
        if not ctx.branch:
            return Response({"detail": "No active branch selected."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = InvoiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        items_input = data.get("items") or []
        if not items_input:
            return Response({"items": ["At least one invoice item is required."]}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            invoice = Invoice.objects.create(
                organization=ctx.organization,
                branch=ctx.branch,
                created_by=request.user,
                customer_name=data["customer_name"].strip(),
                customer_email=(data.get("customer_email") or "").strip() or None,
                customer_phone=(data.get("customer_phone") or "").strip() or None,
                notes=(data.get("notes") or "").strip() or None,
                payment_plan=data.get("payment_plan", "one_time"),
                due_date=data.get("due_date"),
                invoice_number=_generate_invoice_number(ctx.organization),
                status="pending",
            )

            total_amount = 0.0
            for item in items_input:
                inv = Inventory.objects.filter(
                    id=item["inventory_id"],
                    organization=ctx.organization,
                    branch=ctx.branch,
                ).first()
                if not inv:
                    transaction.set_rollback(True)
                    return Response(
                        {"detail": f"Inventory item {item['inventory_id']} not found in active branch."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                unit_price = (
                    float(item["unit_price"])
                    if item.get("unit_price") is not None
                    else float(inv.sale_price or 0.0)
                )
                qty = int(item["quantity"])
                line_total = round(unit_price * qty, 2)
                total_amount += line_total
                InvoiceItem.objects.create(
                    invoice=invoice,
                    organization=ctx.organization,
                    branch=ctx.branch,
                    inventory=inv,
                    quantity=qty,
                    unit_price=unit_price,
                    total=line_total,
                )

            invoice.total_amount = round(total_amount, 2)
            invoice.save(update_fields=["total_amount"])

            actor = _user_display_With_role(request.user, ctx.organization)
            _record_invoice_log(
                invoice=invoice,
                user=request.user,
                action="created",
                summary=f"Invoice created by {actor} via mobile API.",
            )

        invoice.refresh_from_db()
        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


class MobileInvoiceDetailView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner",)
    required_feature_permissions = ("invoices",)

    @extend_schema(tags=["Invoices"])
    def get(self, request, pk):
        ctx = resolve_mobile_context(request)
        invoice = _get_scoped_invoice(request, ctx, pk)
        if not invoice:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(InvoiceSerializer(invoice).data)

    @extend_schema(request=InvoiceUpdateSerializer, tags=["Invoices"])
    def patch(self, request, pk):
        ctx = resolve_mobile_context(request)
        invoice = _get_scoped_invoice(request, ctx, pk)
        if not invoice:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
        if invoice.status in ("paid", "closed"):
            return Response(
                {"detail": f"Cannot edit a {invoice.status} invoice."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = InvoiceUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            for field in ("customer_name", "customer_email", "customer_phone", "notes", "payment_plan", "due_date"):
                if field in data:
                    setattr(invoice, field, data[field])

            if "items" in data:
                if invoice.inventory_deducted:
                    return Response(
                        {"detail": "Cannot modify items after inventory has been deducted by a payment."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                invoice.items.all().delete()
                total_amount = 0.0
                for item in data["items"]:
                    inv = Inventory.objects.filter(
                        id=item["inventory_id"],
                        organization=ctx.organization,
                        branch=invoice.branch,
                    ).first()
                    if not inv:
                        transaction.set_rollback(True)
                        return Response(
                            {"detail": f"Inventory item {item['inventory_id']} not found in invoice branch."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    unit_price = (
                        float(item["unit_price"])
                        if item.get("unit_price") is not None
                        else float(inv.sale_price or 0.0)
                    )
                    qty = int(item["quantity"])
                    line_total = round(unit_price * qty, 2)
                    total_amount += line_total
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        organization=ctx.organization,
                        branch=invoice.branch,
                        inventory=inv,
                        quantity=qty,
                        unit_price=unit_price,
                        total=line_total,
                    )
                invoice.total_amount = round(total_amount, 2)

            invoice.save()
            actor = _user_display_With_role(request.user, ctx.organization)
            _record_invoice_log(
                invoice=invoice,
                user=request.user,
                action="edited",
                summary=f"Invoice updated by {actor} via mobile API.",
            )

        invoice.refresh_from_db()
        return Response(InvoiceSerializer(invoice).data)

    @extend_schema(tags=["Invoices"])
    def delete(self, request, pk):
        ctx = resolve_mobile_context(request)
        if ctx.role != "owner":
            return Response(
                {"detail": "Only organization owners can delete invoices."},
                status=status.HTTP_403_FORBIDDEN,
            )
        invoice = Invoice.objects.filter(id=pk, organization=ctx.organization).first()
        if not invoice:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
        if invoice.inventory_deducted or (invoice.amount_paid or 0) > 0:
            return Response(
                {"detail": "Cannot delete an invoice that already has recorded payments."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MobileInvoiceRecordPaymentView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner",)
    required_feature_permissions = ("invoices",)

    @extend_schema(request=RecordPaymentSerializer, tags=["Invoices"])
    def post(self, request, pk):
        ctx = resolve_mobile_context(request)
        invoice = _get_scoped_invoice(request, ctx, pk)
        if not invoice:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
        if invoice.status in ("paid", "closed"):
            return Response(
                {"detail": f"Cannot record payment on a {invoice.status} invoice."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RecordPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount_now = round(float(serializer.validated_data["amount"]), 2)
        payment_method = serializer.validated_data["payment_method"]
        payment_notes = (serializer.validated_data.get("notes") or "").strip()

        balance = invoice.balance_due
        if amount_now > balance:
            return Response(
                {"amount": [f"Payment amount ({amount_now}) exceeds balance due ({balance})."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        actor = _user_display_With_role(request.user, ctx.organization)
        currency = ctx.organization.currency_symbol

        try:
            with transaction.atomic():
                items = list(invoice.items.select_related("inventory", "inventory__product").all())
                deducted_this_time = False

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
                                inv.status = "Restocking"
                            inv.save()
                    invoice.inventory_deducted = True
                    deducted_this_time = True

                InvoicePayment.objects.create(
                    invoice=invoice,
                    organization=ctx.organization,
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
                    invoice.status = "paid"
                    invoice.save()
                    _create_completed_sale_for_invoice(invoice, payment_method)
                    stock_note = " Inventory deducted." if deducted_this_time else ""
                    _record_invoice_log(
                        invoice=invoice,
                        user=request.user,
                        action="payment_recorded",
                        summary=(
                            f"Payment of {currency}{amount_now:,.2f} ({payment_method}) recorded by {actor}. "
                            f"Payment completed in full.{stock_note}"
                        ),
                    )
                else:
                    invoice.status = "partially_paid"
                    if invoice.payment_plan != "installment":
                        invoice.payment_plan = "installment"
                    invoice.save()
                    stock_note = " Inventory deducted." if deducted_this_time else ""
                    _record_invoice_log(
                        invoice=invoice,
                        user=request.user,
                        action="payment_recorded",
                        summary=(
                            f"Installment of {currency}{amount_now:,.2f} ({payment_method}) recorded by {actor}. "
                            f"Remaining balance: {currency}{remaining_after:,.2f}.{stock_note}"
                        ),
                    )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        owner = ctx.organization.owned_by
        if owner and owner != request.user:
            Notification.objects.create(
                user=owner,
                organization=ctx.organization,
                message=(
                    f"Payment of {currency}{amount_now:,.2f} recorded on Invoice "
                    f"{invoice.invoice_number} by {actor}."
                ),
                notification_type="success" if invoice.status == "paid" else "info",
            )

        invoice.refresh_from_db()
        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_200_OK)


class MobileInvoiceCloseView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner",)
    required_feature_permissions = ("invoices",)

    @extend_schema(tags=["Invoices"])
    def post(self, request, pk):
        ctx = resolve_mobile_context(request)
        invoice = _get_scoped_invoice(request, ctx, pk)
        if not invoice:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
        if invoice.status != "pending" or (invoice.amount_paid or 0) > 0:
            return Response(
                {"detail": "Only unpaid pending invoices can be closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice.status = "closed"
        invoice.save(update_fields=["status"])
        actor = _user_display_With_role(request.user, ctx.organization)
        _record_invoice_log(
            invoice=invoice,
            user=request.user,
            action="closed",
            summary=f"Invoice closed by {actor} via mobile API.",
        )
        return Response(InvoiceSerializer(invoice).data)


class MobileInvoiceReopenView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, IsOwnerOnly]

    @extend_schema(tags=["Invoices"])
    def post(self, request, pk):
        ctx = resolve_mobile_context(request)
        invoice = Invoice.objects.filter(id=pk, organization=ctx.organization).first()
        if not invoice:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
        if invoice.status != "closed":
            return Response(
                {"detail": "Only closed invoices can be reopened."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice.status = "partially_paid" if (invoice.amount_paid or 0) > 0 else "pending"
        invoice.save(update_fields=["status"])
        actor = _user_display_With_role(request.user, ctx.organization)
        _record_invoice_log(
            invoice=invoice,
            user=request.user,
            action="reopened",
            summary=f"Invoice reopened by {actor} via mobile API.",
        )
        return Response(InvoiceSerializer(invoice).data)


class MobileInvoicePdfView(APIView):
    permission_classes = [*MOBILE_DEFAULT_PERMISSIONS, HasRoleOrFeaturePermission]
    allowed_roles = ("owner",)
    required_feature_permissions = ("invoices",)

    @extend_schema(tags=["Invoices"])
    def get(self, request, pk):
        ctx = resolve_mobile_context(request)
        invoice = _get_scoped_invoice(request, ctx, pk)
        if not invoice:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)

        items = invoice.items.select_related("inventory__product").all()
        payments = invoice.payments.select_related("recorded_by").order_by("date_paid")
        template = get_template("ims/invoice_pdf.html")
        html = template.render(
            {
                "invoice": invoice,
                "items": items,
                "payments": payments,
                "branch": invoice.branch,
                "organization": ctx.organization,
            }
        )
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="Invoice_{invoice.invoice_number}.pdf"'
        pisa_status = pisa.CreatePDF(html, dest=response, encoding="utf-8")
        if pisa_status.err:
            return Response(
                {"detail": "Failed to generate PDF."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return response

