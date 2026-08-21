import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from account.decorators import role_required
from account.utils import get_request_organization, get_request_branch
from intelligence.models import Conversation, Message, UserInsight, MorningBriefing
from intelligence.services.conversation_service import ConversationService
from intelligence.services.assistant_service import AssistantService
from intelligence.services.insight_service import InsightService
from intelligence.services.briefing_service import BriefingService

@role_required(roles=['owner'])
@login_required
def chat_session_view(request):
    """
    Renders the assistant chat interface, showing existing threads.
    """
    organization = get_request_organization(request)
    branch = get_request_branch(request, organization)
    
    conversations = ConversationService.get_conversations(organization, branch)
    
    context = {
        'conversations': conversations,
        'branch': branch,
    }
    return render(request, 'intelligence/chat_sidebar.html', context)


@role_required(roles=['owner'])
@login_required
@require_POST
def create_conversation_view(request):
    """
    Creates a new conversation thread.
    """
    organization = get_request_organization(request)
    branch = get_request_branch(request, organization)
    
    title = request.POST.get('title', 'New Session').strip() or 'New Session'
    starting_message = request.POST.get('message', '').strip()
    
    if starting_message:
        title = starting_message[:30] + '...' if len(starting_message) > 30 else starting_message
        
    conversation = ConversationService.create_conversation(
        organization=organization,
        branch=branch,
        user=request.user,
        title=title
    )
    
    if starting_message:
        assistant_service = AssistantService()
        assistant_service.send_message(conversation, starting_message)
        
    if request.headers.get('HX-Request'):
        messages = conversation.messages.all().order_by('timestamp')
        context = {
            'conversation': conversation,
            'messages': messages,
        }
        response = render(request, 'intelligence/partials/chat_window.html', context)
        response['HX-Trigger'] = 'conversationCreated'
        return response
        
    return redirect('chat_session')


@role_required(roles=['owner'])
@login_required
def chat_message_view(request, conversation_id):
    """
    Loads conversation messages or submits a new user prompt.
    """
    organization = get_request_organization(request)
    conversation = get_object_or_404(Conversation, id=conversation_id, organization=organization)
    
    if request.method == 'POST':
        prompt = request.POST.get('message', '').strip()
        if not prompt:
            return HttpResponse(status=204)
            
        assistant_service = AssistantService()
        
        # Check if streaming is requested
        stream_requested = request.GET.get('stream', 'false').lower() == 'true'
        
        if stream_requested:
            # Return SSE stream response
            def event_stream():
                stream = assistant_service.stream_message(conversation, prompt)
                for chunk in stream:
                    yield f"data: {json.dumps({'text': chunk})}\n\n"
                    
            response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
            response['Cache-Control'] = 'no-cache'
            return response
            
        # Synchronous execution
        msg = assistant_service.send_message(conversation, prompt)
        
        if request.headers.get('HX-Request'):
            # Renders updated message thread container list via HTMX
            messages = conversation.messages.all().order_by('timestamp')
            return render(request, 'intelligence/partials/message_list.html', {'messages': messages, 'conversation': conversation})
            
    messages = conversation.messages.all().order_by('timestamp')
    context = {
        'conversation': conversation,
        'messages': messages,
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'intelligence/partials/chat_window.html', context)
    return render(request, 'intelligence/chat.html', context)


@role_required(roles=['owner'])
@login_required
@require_POST
def delete_conversation_view(request, conversation_id):
    """
    Deletes conversation thread securely.
    """
    organization = get_request_organization(request)
    success = ConversationService.delete_conversation(conversation_id, organization)
    if success and request.headers.get('HX-Request'):
        return HttpResponse("", status=200)
    return redirect('chat_session')


@role_required(roles=['owner'])
@login_required
def morning_briefing_widget(request):
    """
    Renders the Morning Briefing dashboard card (lazy-loaded).
    """
    from django.utils import timezone
    from intelligence.tasks import generate_organization_briefing_task
    
    organization = get_request_organization(request)
    today = timezone.now().date()
    
    # Find briefing generated today (excluding Fallback briefings)
    briefing = MorningBriefing.objects.filter(
        organization=organization, 
        date=today
    ).exclude(title__contains="Fallback").first()
    
    # If no briefing exists for today, trigger background generation task
    if not briefing:
        generate_organization_briefing_task.delay(str(organization.id))
        # Fall back to the most recent non-fallback briefing available so dashboard has text
        briefing = MorningBriefing.objects.filter(
            organization=organization
        ).exclude(title__contains="Fallback").first()
        
    return render(request, 'intelligence/widgets/morning_briefing.html', {'briefing': briefing})


@role_required(roles=['owner'])
@login_required
def insights_list_widget(request):
    """
    Displays recent analytical UserInsight alerts on the main dashboard layout.
    """
    from intelligence.tasks import generate_branch_insights_task
    
    organization = get_request_organization(request)
    branch = get_request_branch(request, organization)
    
    insights = InsightService.get_insights(organization, branch, unread_only=True)
    
    # If none found, trigger background scan asynchronously
    if not insights:
        generate_branch_insights_task.delay(str(organization.id), str(branch.id))
        
    return render(request, 'intelligence/widgets/insights_list.html', {'insights': insights})


@role_required(roles=['owner'])
@login_required
@require_POST
def mark_insight_read_view(request, insight_id):
    """
    Dismisses/marks insight as read.
    """
    organization = get_request_organization(request)
    success = InsightService.mark_as_read(insight_id, organization)
    if success and request.headers.get('HX-Request'):
        return HttpResponse("", status=200)
    return JsonResponse({'success': success})
