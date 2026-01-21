from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from datetime import datetime, date
from .models import Sale, ErrorTicket, TicketComment
from account.models import CustomUser, Branch, ActivityLog
from account.emails import send_ticket_created_email
from django.contrib.auth.decorators import login_required
from . forms import *
from django.core.paginator import Paginator
from account.decorators import role_required
from django.db import models
from account.models import CustomUser

# Create your views here

@role_required(roles=['owner'])
@login_required
def branchReport(request):
    organization = request.user.organization
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
    return render(request, 'ims/branchrep.html', context)



@role_required(roles=['owner'])
@login_required
# @is_unsubscribed
def report(request, pk):
    organization = request.user.organization
    branch = get_object_or_404(Branch, id=pk, organization=organization)
    start_date_contains = request.GET.get('start_date')
    end_date_contains = request.GET.get('end_date')
    sale_qs = Sale.objects.filter(branch_id=pk)

    if start_date_contains:
        sale_qs = sale_qs.filter(date_updated__date__gte=start_date_contains)

    if end_date_contains:
        sale_qs = sale_qs.filter(date_updated__date__lte=end_date_contains)

    # Sum on full filtered set (not just current page)
    total_profits = sum(sale_qs.values_list('total_profit', flat=True))

    paginator = Paginator(sale_qs.order_by('-date_updated'), 5)
    page_number = request.GET.get('page')
    sale_page = paginator.get_page(page_number)
    nums = "a" * sale_page.paginator.num_pages

    context = {
        'branch':branch,
        'sale_page': sale_page,
        'total_profits':total_profits,
        'start_date': start_date_contains,
        'end_date': end_date_contains,
        'nums': nums,
    }
    return render(request, 'ims/reports.html', context)



@login_required
# @is_unsubscribed
def errorTicket(request):
    organization = request.user.organization
    user = request.user
    
    # Role-based filtering
    if user.role in ['owner', 'manager']:
        # Owners and managers see all tickets in their organization
        qs = ErrorTicket.objects.filter(organization=organization).order_by('-date_added')
    else:
        # Sales staff see only tickets they created or are assigned to
        qs = ErrorTicket.objects.filter(
            organization=organization
        ).filter(
            models.Q(staff=user) | models.Q(assigned_to=user)
        ).order_by('-date_added')

    status = request.GET.get('status')
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 10)
    page_num = request.GET.get('page')
    ticket_page = paginator.get_page(page_num)
    nums = "a" * ticket_page.paginator.num_pages

    # Add form for modal
    form = CreateTicketForm(organization=organization)
    
    # Get staff members for assignment dropdown
    
    staff = CustomUser.objects.filter(organization=organization, role__in=['manager', 'sales']).order_by('first_name')

    context = {
        'ticket': ticket_page,
        'pending': qs.filter(status='Pending').count(),
        'nums': nums,
        'current_status': status or '',
        'form': form,
        'can_assign': user.role in ['owner', 'manager'],
        'staff': staff,
    }

    return render(request, 'ims/ticket.html', context)

@login_required
# @is_unsubscribed
def Ticket(request, pk):
    organization = request.user.organization
    user = request.user
    
    # Get ticket with role-based access check
    if user.role in ['owner', 'manager']:
        ticket = get_object_or_404(ErrorTicket, id=pk, organization=organization)
    else:
        # Sales staff can only access their own tickets or tickets assigned to them
        ticket = get_object_or_404(
            ErrorTicket,
            id=pk,
            organization=organization
        )
        if ticket.staff != user and ticket.assigned_to != user:
            messages.error(request, 'You do not have permission to view this ticket')
            return redirect('ticket')
    
    form = UpdateTicketForm(instance=ticket, organization=organization)
    comment_form = TicketCommentForm()
    can_assign = user.role in ['owner', 'manager']

    if request.method == 'POST':
        if 'content' in request.POST:
            comment_form = TicketCommentForm(request.POST)
            if comment_form.is_valid():
                TicketComment.objects.create(
                    ticket=ticket,
                    author=request.user,
                    content=comment_form.cleaned_data['content']
                )
                messages.success(request, 'Comment added')
                return redirect('tickets', pk=ticket.id)
        else:
            # Only owners and managers can update status and assignment
            if not can_assign:
                messages.error(request, 'You do not have permission to update this ticket')
                return redirect('tickets', pk=ticket.id)
            
            form = UpdateTicketForm(request.POST, instance=ticket, organization=organization)
            if form.is_valid():
                form.save()
                messages.success(request, 'Ticket updated')
                return redirect('ticket')

    comments = ticket.comments.order_by('created_at')
    context = {
        'ticket': ticket,
        'form': form,
        'comment_form': comment_form,
        'comments': comments,
        'can_assign': can_assign,
    }
    return render(request, 'ims/view_ticket.html', context)

@login_required
# @is_unsubscribed
def createTicket(request):
    form = CreateTicketForm(organization=request.user.organization)
    if request.method == 'POST':
        form = CreateTicketForm(request.POST or None, organization=request.user.organization)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.organization = request.user.organization
            ticket.staff = request.user
            ticket.branch = request.user.branch
            ticket.save()
            
            # Send notification email if ticket is assigned to someone
            if ticket.assigned_to:
                send_ticket_created_email(ticket, ticket.assigned_to, request.user.organization)
            
            messages.success(request, 'Ticket created successfully')
            return redirect('ticket')

    return render(request, 'ims/create_ticket.html', {'form': form})
