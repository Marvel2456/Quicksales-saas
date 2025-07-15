from django.urls import path
from . import views
from ims.view.dashboard_views import branchDasboard, dashboard, staffDashboard
from ims.view.category_views import category_list, category, edit_category, delete_category
from ims.view.product_views import product_category, product, edit_product, delete_product
from ims.view.inventory_views import (
    edit_inventory, inventory_list, branchInventory, delete_inventory, restock, adminRestock,
    inventoryView, inventoryAudit, export_audit_csv
)


urlpatterns = [

    # Dashboard URLs
    path('', branchDasboard, name='index'),
    path('branchdash/<str:pk>/', dashboard, name='branchdash'),
    path('dashboard/', staffDashboard, name='dashboard'),



    # Category URLs
    path('category_list/', category_list, name='category_list'),
    path('category/<str:pk>/', category, name='category'),
    path('edit_category/', edit_category, name='edit_category'),
    path('category_delete/', delete_category, name='category_delete'),



    # Product URLs
    path('products/', product_category, name='products'),
    path('product/<str:pk>/', product, name='product'),
    path('edit_product/', edit_product, name='edit_product'),
    path('delete_product/', delete_product, name='delete_product'),



    # Inventory URLs
    path('set_reorder/', edit_inventory, name='set_reorder'),
    path('inventorys/', inventory_list, name='inventorys'),
    path('branchinv/', branchInventory, name='branchinv'),
    path('delete_inventory/', delete_inventory, name='delete_inventory'),
    path('restock/', restock, name='restock'),
    path('adminrestock/', adminRestock, name='adminrestock'),
    path('productlist/<str:pk>/', inventoryView, name='productlist'),
    path('price_audit/<str:pk>/', inventoryAudit, name='price_audit'),
    path('export_audit/<str:pk>/', export_audit_csv, name= 'export_audit'),


    # Other URLs

    path('update_cart/', views.updateCart, name='update_cart'),
    path('update_quantity/', views.updateQuantity, name='update_quantity'),
    path('cart/', views.cart, name='cart'),
    path('completed/<int:pk>/', views.sale_complete, name='completed'),
    path('checkout/', views.checkout, name='checkout'),
    
    path('reciept/<str:pk>/', views.reciept, name='reciept'),
    
    path('branchstore/', views.branchStore, name='branchstore'),
    path('store/', views.store, name='store'),
    
    path('sales/', views.sales, name='sales'),
    path('sales<int:pk>/', views.sales, name='sales_single'),
    path('sales_delete/', views.sale_delete, name='sales_delete'),
    path('records/', views.record, name='records'),
    
   
    path('staff/', views.staffs, name='staff'),
    path('staff_detail/<str:pk>/', views.staff, name='staff_detail'),
    path('edit_staff/', views.edit_staff, name='edit_staff'),
    path('delete_staff/', views.delete_staff, name='delete_staff'),
    
    path('export_sales', views.export_sales_csv, name= 'export_sales'),
    path('export_profit/<int:pk>/export/', views.export_profit_csv, name= 'export_profit'),
    
    path('profitData/<str:pk>/', views.profitData, name='profitData'),
    path('branchaudit/', views.branchAudit, name='branchaudit'),
    
    path('ticket/', views.errorTicket, name='ticket'),
    path('create_ticket/', views.createTicket, name='create_ticket'),
    path('tickets/<str:pk>', views.Ticket, name='tickets'),
    path('branchrep/', views.branchReport, name='branchrep'),
    path('reports/<int:pk>/', views.report, name='reports'),
    path('branchcount/', views.branchCount, name='branchcount'),
    path('count/', views.countView, name='count'),
    path('admincount/<str:pk>/', views.adminCountView, name='admincount'),
    path('addcount/', views.addCount, name='addcount'),
    
    path('sale-pdf/', views.sale_pdf, name='sale-pdf'),
]
# watch out if the value of the variance changes or it is stamped to each date
# what happens when users logs in to another POS and makes sale note: should not be possible
