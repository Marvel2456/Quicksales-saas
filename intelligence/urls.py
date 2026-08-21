from django.urls import path
from . import views

urlpatterns = [
    path('chat/', views.chat_session_view, name='chat_session'),
    path('chat/create/', views.create_conversation_view, name='create_conversation'),
    path('chat/<uuid:conversation_id>/', views.chat_message_view, name='chat_message'),
    path('chat/<uuid:conversation_id>/delete/', views.delete_conversation_view, name='delete_conversation'),
    path('widget/morning-briefing/', views.morning_briefing_widget, name='morning_briefing_widget'),
    path('widget/insights/', views.insights_list_widget, name='insights_list_widget'),
    path('insight/<uuid:insight_id>/read/', views.mark_insight_read_view, name='mark_insight_read'),
]
