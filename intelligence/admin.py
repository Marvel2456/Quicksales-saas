from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .models import AIConfiguration, Conversation, Message, UserInsight, MorningBriefing

class MessageInline(TabularInline):
    model = Message
    extra = 0
    fields = ('role', 'content', 'timestamp')
    readonly_fields = ('role', 'content', 'timestamp')
    can_delete = False


@admin.register(AIConfiguration)
class AIConfigurationAdmin(ModelAdmin):
    list_display = ('active_provider', 'model_name', 'is_active', 'updated_at')
    list_filter = ('active_provider', 'is_active')
    ordering = ('-updated_at',)


@admin.register(Conversation)
class ConversationAdmin(ModelAdmin):
    list_display = ('title', 'organization', 'branch', 'created_by', 'created_at', 'updated_at')
    search_fields = ('title', 'organization__name', 'created_by__email')
    list_filter = ('organization', 'branch', 'created_at')
    ordering = ('-updated_at',)
    raw_id_fields = ('organization', 'branch', 'created_by')
    autocomplete_fields = ('organization', 'branch', 'created_by')
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(ModelAdmin):
    list_display = ('conversation_title', 'role', 'content_excerpt', 'timestamp')
    search_fields = ('conversation__title', 'content', 'role')
    list_filter = ('role', 'timestamp')
    ordering = ('-timestamp',)
    raw_id_fields = ('conversation',)
    autocomplete_fields = ('conversation',)

    def conversation_title(self, obj):
        return obj.conversation.title
    conversation_title.short_description = 'Conversation'

    def content_excerpt(self, obj):
        if obj.content:
            return obj.content[:80] + '...' if len(obj.content) > 80 else obj.content
        if obj.tool_calls:
            return f"[Tool Call Request: {', '.join([c.get('function', {}).get('name', '') for c in obj.tool_calls])}]"
        return '[Empty]'
    content_excerpt.short_description = 'Content Excerpt'


@admin.register(UserInsight)
class UserInsightAdmin(ModelAdmin):
    list_display = ('title', 'organization', 'branch', 'insight_type', 'is_read', 'created_at')
    search_fields = ('title', 'content', 'organization__name')
    list_filter = ('insight_type', 'is_read', 'created_at', 'organization')
    ordering = ('-created_at',)
    raw_id_fields = ('organization', 'branch')
    autocomplete_fields = ('organization', 'branch')


@admin.register(MorningBriefing)
class MorningBriefingAdmin(ModelAdmin):
    list_display = ('title', 'organization', 'date', 'created_at')
    search_fields = ('title', 'content', 'organization__name')
    list_filter = ('date', 'created_at', 'organization')
    ordering = ('-date', '-created_at')
    raw_id_fields = ('organization',)
    autocomplete_fields = ('organization',)
