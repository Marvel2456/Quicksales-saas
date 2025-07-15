from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from datetime import datetime, date
from .models import Sale, ErrorTicket
from account.models import CustomUser, Branch, ActivityLog
from django.contrib.auth.decorators import login_required
from . forms import *
from django.core.paginator import Paginator
from account.decorators import role_required


# Create your views here

@role_required(roles=['owner'])
@login_required
# @is_unsubscribed
def branchReport(request):
    organization = request.user.organization
    branch = Branch.objects.filter(organization=organization).all()

    context = {
        'branch':branch
    }
    return render(request, 'ims/branchrep.html', context)

@role_required(roles=['owner'])
@login_required
# @is_unsubscribed
def report(request, pk):
    organization = request.user.organization
    branch = get_object_or_404(Branch, id=pk, organization=organization)
    now = datetime.now()
    start_date_contains = request.GET.get('start_date')
    end_date_contains = request.GET.get('end_date')
    sale = Sale.objects.filter(branch_id = pk)

    if start_date_contains != '' and start_date_contains is not None:
        sale = sale.filter(date_updated__gte=start_date_contains)

    if end_date_contains != '' and end_date_contains is not None:
        sale = sale.filter(date_updated__lt=end_date_contains)
    
    
    total_profits = sum(sale.values_list('total_profit', flat=True))
    

    context = {
        'branch':branch,
        'sale':sale,
        'total_profits':total_profits,
    }
    return render(request, 'ims/reports.html', context)



@login_required
# @is_unsubscribed
def errorTicket(request):
    ticket = ErrorTicket.objects.all()
    pending = ErrorTicket.objects.filter(status='Pending')

    context = {
        'ticket':ticket,
        'pending':pending
    }

    return render(request, 'ims/ticket.html', context)

@login_required
# @is_unsubscribed
def Ticket(request, pk):
    ticket = ErrorTicket.objects.get(id=pk)
    form = UpdateTicketForm(instance=ticket)
    if request.method == 'POST':
        form = UpdateTicketForm(request.POST, instance=ticket)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ticket viewed')
            return redirect('ticket')

    context = {
        'ticket':ticket
    }
    return render(request, 'ims/view_ticket.html', context)

@login_required
# @is_unsubscribed
def createTicket(request):
    staff = CustomUser.objects.all()
    form = CreateTicketForm()
    if request.method == 'POST':
        form = CreateTicketForm(request.POST or None)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.staff = request.user
            ticket.pos = ticket.staff.pos
            ticket.branch = ticket.staff.branch
            ticket.save()
            messages.success(request, 'Ticket Created Successfully')
            return redirect('create_ticket')

    context = {
        'staff':staff
    }
    
    return render(request, 'ims/create_ticket.html', context)
