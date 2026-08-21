import uuid
from django.db import models
from django.utils import timezone
from account.models import Organization, Branch, CustomUser

class AIConfiguration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    PROVIDER_CHOICES = [
        ('gemini', 'Google Gemini'),
        ('openrouter', 'OpenRouter (Groq/Claude)'),
        ('local', 'Local LLM (Ollama/vLLM)'),
    ]
    active_provider = models.CharField(max_length=50, choices=PROVIDER_CHOICES, default='gemini')
    model_name = models.CharField(max_length=150, default='gemini-flash-latest')
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI Configuration"
        verbose_name_plural = "AI Configurations"

    def save(self, *args, **kwargs):
        # Enforce singleton behavior by deactivating others when saving an active one
        if self.is_active:
            AIConfiguration.objects.exclude(id=self.id).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()

    def __str__(self):
        return f"{self.get_active_provider_display()} ({self.model_name}) - Active: {self.is_active}"


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='ai_conversations')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_conversations')
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_conversations')
    title = models.CharField(max_length=255, default='New Conversation')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['organization', '-updated_at']),
        ]

    def __str__(self):
        return f"{self.title} ({self.organization.name})"


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    ROLE_CHOICES = [
        ('system', 'System'),
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('tool', 'Tool'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(blank=True, null=True)
    tool_calls = models.JSONField(blank=True, null=True) # Holds tool call requests details if assistant requests them
    name = models.CharField(max_length=150, blank=True, null=True) # Mapping name for tool output results
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['conversation', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.role.capitalize()}: {self.content[:50] if self.content else '[Tool Call]'}"


class UserInsight(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='ai_insights')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_insights')
    INSIGHT_TYPE_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('success', 'Success'),
        ('error', 'Error'),
    ]
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPE_CHOICES, default='info')
    title = models.CharField(max_length=255)
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
        ]

    def __str__(self):
        return f"[{self.insight_type.upper()}] {self.title} ({self.organization.name})"


class MorningBriefing(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='ai_morning_briefings')
    title = models.CharField(max_length=255, default='Daily Morning Briefing')
    content = models.TextField()
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['organization', '-date']),
        ]

    def __str__(self):
        return f"Briefing for {self.date} - {self.organization.name}"
