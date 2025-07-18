from django.urls import path
from . import views
from ims.view.dashboard_views import branchDasboard, dashboard, staffDashboard
from ims.view.category_views import (
    category_list, category, edit_category, delete_category, branch_category
)
from ims.view.product_views import product_category, product, edit_product, delete_product, branch_product
from ims.view.inventory_views import (
    edit_inventory, inventory_list, branchInventory, delete_inventory, restock, adminRestock,
    inventoryView
)
from ims.view.audit_views import (
    inventoryAudit, export_audit_csv, branchCount, countView, adminCountView, addCount, branchAudit
)
from ims.view.sale_views import (
    sale_complete, checkout, reciept, branchStore, store, sales, sale_delete, sale_pdf,
    updateCart, updateQuantity, cart, export_sales_csv, export_profit_csv, profitData
)
from ims.view.team_views import staffs, staff, edit_staff, delete_staff, record




urlpatterns = [

    # Dashboard URLs
    path('', branchDasboard, name='index'),
    path('branchdash/<str:pk>/', dashboard, name='branchdash'),
    path('dashboard/', staffDashboard, name='dashboard'),



    # Category URLs
    path('category_list/<str:pk>/', category_list, name='category_list'),
    path('category/<str:pk>/', category, name='category'),
    path('edit_category/<uuid:pk>/', edit_category, name='edit_category'),
    path('category_delete/<uuid:pk>/', delete_category, name='category_delete'),
    path('branch_category/', branch_category, name='branch_category'),
    # path('admin_category/<str:pk>/', AdminCategory, name='admin_category'),



    # Product URLs
    path('products/<str:pk>/', product_category, name='products'),
    path('product/<str:pk>/', product, name='product'),
    path('edit_product/<uuid:pk>/', edit_product, name='edit_product'),
    path('delete_product/', delete_product, name='delete_product'),
    path('branch_product/', branch_product, name='branch_product'),




    # Inventory URLs
    path('set_reorder/', edit_inventory, name='set_reorder'),
    path('inventorys/', inventory_list, name='inventorys'),
    path('branchinv/', branchInventory, name='branchinv'),
    path('delete_inventory/', delete_inventory, name='delete_inventory'),
    path('restock/', restock, name='restock'),
    path('adminrestock/', adminRestock, name='adminrestock'),
    path('productlist/<str:pk>/', inventoryView, name='productlist'),
    




    #  Audit URLs
    path('price_audit/<str:pk>/', inventoryAudit, name='price_audit'),
    path('export_audit/<str:pk>/', export_audit_csv, name= 'export_audit'),
    path('branchcount/', branchCount, name='branchcount'),
    path('count/', countView, name='count'),
    path('admincount/<str:pk>/', adminCountView, name='admincount'),
    path('addcount/', addCount, name='addcount'),
    path('branchaudit/', branchAudit, name='branchaudit'),





    # Sale URLs
    path('update_cart/', updateCart, name='update_cart'),
    path('update_quantity/', updateQuantity, name='update_quantity'),
    path('cart/', cart, name='cart'),
    path('completed/<int:pk>/', sale_complete, name='completed'),
    path('checkout/', checkout, name='checkout'),
    path('reciept/<str:pk>/', reciept, name='reciept'),
    path('branchstore/', branchStore, name='branchstore'),
    path('store/', store, name='store'),
    path('sales/', sales, name='sales'),
    path('sales<int:pk>/', sales, name='sales_single'),
    path('sales_delete/', sale_delete, name='sales_delete'),
    path('export_sales', export_sales_csv, name= 'export_sales'),
    path('export_profit/<int:pk>/export/', export_profit_csv, name= 'export_profit'),
    path('profitData/<str:pk>/', profitData, name='profitData'),
    path('sale-pdf/', sale_pdf, name='sale-pdf'),
    




    #  Team URLs
    path('staff/', staffs, name='staff'),
    path('staff_detail/<str:pk>/', staff, name='staff_detail'),
    path('edit_staff/', edit_staff, name='edit_staff'),
    path('delete_staff/', delete_staff, name='delete_staff'),
    path('records/', record, name='records'),




    # Other URLs
    path('ticket/', views.errorTicket, name='ticket'),
    path('create_ticket/', views.createTicket, name='create_ticket'),
    path('tickets/<str:pk>', views.Ticket, name='tickets'),
    path('branchrep/', views.branchReport, name='branchrep'),
    path('reports/<int:pk>/', views.report, name='reports'),
    
    
    
]
# watch out if the value of the variance changes or it is stamped to each date
# what happens when users logs in to another POS and makes sale note: should not be possible
