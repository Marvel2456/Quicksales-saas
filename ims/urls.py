from django.urls import path
from . import views
from ims.view.dashboard_views import branchDasboard, dashboard, staffDashboard
from ims.view.category_views import (
    category_list, category, edit_category, delete_category, branch_category
)
from ims.view.product_views import product_category, product, edit_product, delete_product, branch_product, upload_product
from ims.view.inventory_views import (
    edit_inventory, inventory_list, delete_inventory, restock,
    inventoryView, branch_inventory, inventory
)
from ims.view.audit_views import (
    inventoryAudit, export_audit_csv, branchCount, countView, adminCountView, addCount, branchAudit,
    uploadCountBulk, exportCountHistory
)
from ims.view.sale_views import (
    sale_complete, checkout, reciept, branchStore, store, sales, sale_pdf, branchSales,
    updateCart, updateQuantity, cart, export_sales_csv, export_profit_csv, profitData,
    create_new_sale, switch_sale, cancel_sale
)
from ims.view.team_views import (staffs, staff, edit_staff, delete_staff, record, 
                                 branchTeam, branchRecord)
from ims.view.test_signal_view import test_low_stock_signal_view




urlpatterns = [

    # Dashboard URLs
    path('', branchDasboard, name='index'),
    path('branchdash/<str:pk>/', dashboard, name='branchdash'),
    path('dashboard/', staffDashboard, name='dashboard'),



    # Category URLs
    path('category_list/<uuid:pk>/', category_list, name='category_list'),
    path('category/<uuid:pk>/', category, name='category'),
    path('edit_category/<uuid:pk>/', edit_category, name='edit_category'),
    path('category_delete/<uuid:pk>/', delete_category, name='category_delete'),
    path('branch_category/', branch_category, name='branch_category'),
    # path('admin_category/<str:pk>/', AdminCategory, name='admin_category'),



    # Product URLs
    path('products/<str:pk>/', product_category, name='products'),
    path('product/<str:pk>/', product, name='product'),
    path('edit_product/<uuid:pk>/', edit_product, name='edit_product'),
    path('delete_product/<str:pk>/', delete_product, name='delete_product'),
    path('branch_product/', branch_product, name='branch_product'),
    path('product-upload/', upload_product, name='product_upload'),




    # Inventory URLs
    path('set_reorder/<uuid:pk>/', edit_inventory, name='set_reorder'),
    path('inventorys/<str:pk>/', inventory_list, name='inventorys'),
    path('inventory/<str:pk>/', inventory, name='inventory'),
    # path('edit_inventory', edit_inventory, name='edit_inventory'),
    path('branch_inventory', branch_inventory, name='branch_inventory'),
    path('delete_inventory/', delete_inventory, name='delete_inventory'),
    path('restock/<uuid:pk>/', restock, name='restock'),
    # path('adminrestock/', adminRestock, name='adminrestock'),
    path('productlist/<str:pk>/', inventoryView, name='productlist'),
    




    #  Audit URLs
    path('price_audit/<str:pk>/', inventoryAudit, name='price_audit'),
    path('export_audit/<str:pk>/', export_audit_csv, name= 'export_audit'),
    path('branchcount/', branchCount, name='branchcount'),
    path('count/', countView, name='count'),
    path('admincount/<str:pk>/', adminCountView, name='admincount'),
    path('addcount/', addCount, name='addcount'),
    path('upload_count/', uploadCountBulk, name='upload_count'),
    path('export_count/', exportCountHistory, name='export_count'),
    path('branchaudit/', branchAudit, name='branchaudit'),





    # Sale URLs
    path('update_cart/<uuid:pk>/', updateCart, name='update_cart'),
    path('update_quantity/<uuid:pk>/', updateQuantity, name='update_quantity'),
    path('cart/<uuid:pk>/', cart, name='cart'),
    path('completed/<uuid:pk>/', sale_complete, name='completed'),
    path('checkout/<uuid:pk>/', checkout, name='checkout'),
    path('reciept/<uuid:pk>/', reciept, name='reciept'),
    path('branchstore/', branchStore, name='branchstore'),
    path('store/<uuid:pk>/', store, name='store'),
    path('branchsales/', branchSales, name='branchsales'),
    path('sales/<uuid:pk>/', sales, name='sales'),
    path('sale<int:pk>/', sales, name='sales_single'),
    # path('sales_delete/', sale_delete, name='sales_delete'),
    path('export_sales/<uuid:pk>/', export_sales_csv, name= 'export_sales'),
    path('export_profit/<uuid:pk>/export/', export_profit_csv, name= 'export_profit'),
    path('profitData/<str:pk>/', profitData, name='profitData'),
    
    # Multiple concurrent sales URLs
    path('sale/<uuid:pk>/new/', create_new_sale, name='create_new_sale'),
    path('sale/<uuid:pk>/switch/<uuid:sale_id>/', switch_sale, name='switch_sale'),
    path('sale/<uuid:pk>/cancel/<uuid:sale_id>/', cancel_sale, name='cancel_sale'),
    
    path('sale-pdf/<uuid:pk>/', sale_pdf, name='sale-pdf'),
    




    #  Team URLs
    path('branchteam/', branchTeam, name='branchteam'),
    path('staff/<uuid:pk>/', staffs, name='staff'),
    path('staff_detail/<str:pk>/', staff, name='staff_detail'),
    path('edit_staff/', edit_staff, name='edit_staff'),
    path('delete_staff/', delete_staff, name='delete_staff'),
    path('branchrecord/', branchRecord, name='branchrecord'),
    path('records/<uuid:pk>/', record, name='records'),




    # Other URLs
    path('ticket/', views.errorTicket, name='ticket'),
    path('create_ticket/', views.createTicket, name='create_ticket'),
    path('tickets/<str:pk>', views.Ticket, name='tickets'),
    path('branchrep/', views.branchReport, name='branchrep'),
    path('reports/<uuid:pk>/', views.report, name='reports'),
    
    # Test URL - remove in production
    path('test-low-stock-signal/', test_low_stock_signal_view, name='test_low_stock_signal'),
    
    
]
# watch out if the value of the variance changes or it is stamped to each date
# what happens when users logs in to another POS and makes sale note: should not be possible
