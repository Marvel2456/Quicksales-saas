from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from api.views.auth_views import (
    MobileChangePasswordView,
    MobileForgotPasswordView,
    MobileLoginView,
    MobileLogoutView,
    MobileMeView,
    MobileNotificationListView,
    MobileNotificationMarkAllReadView,
    MobileNotificationReadView,
    MobileOrganizationsView,
    MobileRegisterView,
    MobileResendVerificationView,
)
from api.views.catalog_views import (
    MobileCategoryDetailView,
    MobileCategoryListCreateView,
    MobileInventoryCountView,
    MobileInventoryDetailView,
    MobileInventoryListCreateView,
    MobileInventoryRestockView,
    MobileProductDetailView,
    MobileProductListCreateView,
)
from api.views.dashboard_views import (
    MobileBranchDetailView,
    MobileBranchListCreateView,
    MobileDashboardSummaryView,
)
from api.views.extras_views import (
    MobileCountBulkView,
    MobileCountSheetView,
    MobilePriceAuditView,
    MobileProfitReportView,
    MobileSaleProfitDetailView,
    MobileTicketCommentCreateView,
    MobileTicketDetailView,
    MobileTicketListCreateView,
)
from api.views.invoice_views import (
    MobileInvoiceCloseView,
    MobileInvoiceDetailView,
    MobileInvoiceListCreateView,
    MobileInvoicePdfView,
    MobileInvoiceRecordPaymentView,
    MobileInvoiceReopenView,
)
from api.views.pos_views import (
    MobilePOSCatalogView,
    MobilePOSCheckoutView,
    MobilePOSOpenSalesView,
    MobilePOSSyncOfflineView,
    MobileSaleDetailView,
    MobileSaleListView,
)
from api.views.reports_views import (
    MobileActivityLogListView,
    MobileCurrentSubscriptionView,
    MobileErrorTicketDetailView,
    MobileErrorTicketListView,
    MobilePlanListView,
    MobileSalesReportSummaryView,
)
from api.views.staff_views import (
    MobileStaffDetailView,
    MobileStaffListCreateView,
    MobileStaffPermissionChoicesView,
)
from api.views.store_views import (
    MobileBankAccountUpdateView,
    MobileOnlineOrderActionView,
    MobileOnlineOrderDetailView,
    MobileOnlineOrderListView,
    MobilePayoutListCreateView,
    MobileProductListingDetailView,
    MobileProductListingListCreateView,
    MobileServiceDetailView,
    MobileServiceEnrollmentListView,
    MobileServiceListCreateView,
    MobileStoreCustomersView,
    MobileStoreDiscountDetailView,
    MobileStoreDiscountListCreateView,
    MobileStoreSettingsView,
    MobileWalletView,
)

urlpatterns = [
    # Auth & Account
    path("auth/login/", MobileLoginView.as_view(), name="mobile-auth-login"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="mobile-auth-refresh"),
    path("auth/logout/", MobileLogoutView.as_view(), name="mobile-auth-logout"),
    path("auth/register/", MobileRegisterView.as_view(), name="mobile-auth-register"),
    path("auth/resend-verification/", MobileResendVerificationView.as_view(), name="mobile-auth-resend-verification"),
    path("auth/forgot-password/", MobileForgotPasswordView.as_view(), name="mobile-auth-forgot-password"),
    path("auth/change-password/", MobileChangePasswordView.as_view(), name="mobile-auth-change-password"),
    path("account/me/", MobileMeView.as_view(), name="mobile-account-me"),
    path("account/organizations/", MobileOrganizationsView.as_view(), name="mobile-account-organizations"),
    path("notifications/", MobileNotificationListView.as_view(), name="mobile-notifications-list"),
    path("notifications/mark-all-read/", MobileNotificationMarkAllReadView.as_view(), name="mobile-notifications-mark-all-read"),
    path("notifications/<uuid:pk>/read/", MobileNotificationReadView.as_view(), name="mobile-notifications-read"),

    # Dashboard & Branches
    path("dashboard/summary/", MobileDashboardSummaryView.as_view(), name="mobile-dashboard-summary"),
    path("branches/", MobileBranchListCreateView.as_view(), name="mobile-branches-list-create"),
    path("branches/<uuid:pk>/", MobileBranchDetailView.as_view(), name="mobile-branches-detail"),

    # POS, Walk-In Sales & Offline Sync
    path("pos/catalog/", MobilePOSCatalogView.as_view(), name="mobile-pos-catalog"),
    path("pos/open-sales/", MobilePOSOpenSalesView.as_view(), name="mobile-pos-open-sales"),
    path("pos/checkout/", MobilePOSCheckoutView.as_view(), name="mobile-pos-checkout"),
    path("pos/sync-offline/", MobilePOSSyncOfflineView.as_view(), name="mobile-pos-sync-offline"),
    path("sales/", MobileSaleListView.as_view(), name="mobile-sales-list"),
    path("sales/<uuid:pk>/", MobileSaleDetailView.as_view(), name="mobile-sales-detail"),

    # Invoices & Installments
    path("invoices/", MobileInvoiceListCreateView.as_view(), name="mobile-invoices-list-create"),
    path("invoices/<uuid:pk>/", MobileInvoiceDetailView.as_view(), name="mobile-invoices-detail"),
    path("invoices/<uuid:pk>/record-payment/", MobileInvoiceRecordPaymentView.as_view(), name="mobile-invoices-record-payment"),
    path("invoices/<uuid:pk>/close/", MobileInvoiceCloseView.as_view(), name="mobile-invoices-close"),
    path("invoices/<uuid:pk>/reopen/", MobileInvoiceReopenView.as_view(), name="mobile-invoices-reopen"),
    path("invoices/<uuid:pk>/pdf/", MobileInvoicePdfView.as_view(), name="mobile-invoices-pdf"),

    # Categories, Products & Inventory
    path("categories/", MobileCategoryListCreateView.as_view(), name="mobile-categories-list-create"),
    path("categories/<uuid:pk>/", MobileCategoryDetailView.as_view(), name="mobile-categories-detail"),
    path("products/", MobileProductListCreateView.as_view(), name="mobile-products-list-create"),
    path("products/<uuid:pk>/", MobileProductDetailView.as_view(), name="mobile-products-detail"),
    path("inventory/", MobileInventoryListCreateView.as_view(), name="mobile-inventory-list-create"),
    path("inventory/<uuid:pk>/", MobileInventoryDetailView.as_view(), name="mobile-inventory-detail"),
    path("inventory/<uuid:pk>/restock/", MobileInventoryRestockView.as_view(), name="mobile-inventory-restock"),
    path("inventory/<uuid:pk>/count/", MobileInventoryCountView.as_view(), name="mobile-inventory-count"),

    # Staff & Permissions
    path("staff/", MobileStaffListCreateView.as_view(), name="mobile-staff-list-create"),
    path("staff/permission-choices/", MobileStaffPermissionChoicesView.as_view(), name="mobile-staff-permission-choices"),
    path("staff/<uuid:pk>/", MobileStaffDetailView.as_view(), name="mobile-staff-detail"),

    # Reports, Activity Logs & Error Tickets
    path("reports/sales-summary/", MobileSalesReportSummaryView.as_view(), name="mobile-reports-sales-summary"),
    path("activity-logs/", MobileActivityLogListView.as_view(), name="mobile-activity-logs"),
    path("error-tickets/", MobileErrorTicketListView.as_view(), name="mobile-error-tickets-list"),
    path("error-tickets/<uuid:pk>/", MobileErrorTicketDetailView.as_view(), name="mobile-error-tickets-detail"),

    # Subscriptions
    path("subscriptions/current/", MobileCurrentSubscriptionView.as_view(), name="mobile-subscriptions-current"),
    path("subscriptions/plans/", MobilePlanListView.as_view(), name="mobile-subscriptions-plans"),

    # Online Store, Orders, Services & Payouts (Phase 3)
    path("store/settings/", MobileStoreSettingsView.as_view(), name="mobile-store-settings"),
    path("store/listings/", MobileProductListingListCreateView.as_view(), name="mobile-store-listings"),
    path("store/listings/<uuid:pk>/", MobileProductListingDetailView.as_view(), name="mobile-store-listings-detail"),
    path("store/orders/", MobileOnlineOrderListView.as_view(), name="mobile-store-orders"),
    path("store/orders/<uuid:pk>/", MobileOnlineOrderDetailView.as_view(), name="mobile-store-orders-detail"),
    path("store/orders/<uuid:pk>/action/", MobileOnlineOrderActionView.as_view(), name="mobile-store-orders-action"),
    path("store/services/", MobileServiceListCreateView.as_view(), name="mobile-store-services"),
    path("store/services/enrollments/", MobileServiceEnrollmentListView.as_view(), name="mobile-store-services-enrollments"),
    path("store/services/<uuid:pk>/", MobileServiceDetailView.as_view(), name="mobile-store-services-detail"),
    path("store/wallet/", MobileWalletView.as_view(), name="mobile-store-wallet"),
    path("store/bank-account/", MobileBankAccountUpdateView.as_view(), name="mobile-store-bank-account"),
    path("store/payouts/", MobilePayoutListCreateView.as_view(), name="mobile-store-payouts"),
    path("store/discounts/", MobileStoreDiscountListCreateView.as_view(), name="mobile-store-discounts"),
    path("store/discounts/<uuid:pk>/", MobileStoreDiscountDetailView.as_view(), name="mobile-store-discounts-detail"),
    path("store/customers/", MobileStoreCustomersView.as_view(), name="mobile-store-customers"),

    # Price Audit, Stock Count Sheet, Profit Report & Tickets
    path("price-audit/", MobilePriceAuditView.as_view(), name="mobile-price-audit"),
    path("count/", MobileCountSheetView.as_view(), name="mobile-count-sheet"),
    path("count/bulk/", MobileCountBulkView.as_view(), name="mobile-count-bulk"),
    path("reports/profit/", MobileProfitReportView.as_view(), name="mobile-reports-profit"),
    path("reports/profit/sale/<uuid:pk>/", MobileSaleProfitDetailView.as_view(), name="mobile-reports-profit-sale"),
    path("tickets/", MobileTicketListCreateView.as_view(), name="mobile-tickets-list-create"),
    path("tickets/<uuid:pk>/", MobileTicketDetailView.as_view(), name="mobile-tickets-detail"),
    path("tickets/<uuid:pk>/comments/", MobileTicketCommentCreateView.as_view(), name="mobile-tickets-comments"),
]

