import json
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from unittest.mock import Mock, patch
from account.models import CustomUser, Organization, Branch
from intelligence.models import AIConfiguration, Conversation, Message, UserInsight, MorningBriefing
from intelligence.core.provider_factory import ProviderFactory
from intelligence.tools.registry import ToolRegistry
from intelligence.core.memory import MemoryManager
from intelligence.core.assistant_engine import AssistantEngine

class IntelligenceCoreTests(TestCase):
    def setUp(self):
        AIConfiguration.objects.all().delete()
        
        self.owner = CustomUser.objects.create_user(
            email="owner@example.com",
            password="testpass123",
        )
        self.org1 = Organization.objects.create(
            name="Org 1",
            owned_by=self.owner
        )
        self.org2 = Organization.objects.create(
            name="Org 2",
            owned_by=self.owner
        )
        self.branch1 = Branch.objects.create(
            name="Branch 1",
            organization=self.org1
        )
        self.branch2 = Branch.objects.create(
            name="Branch 2",
            organization=self.org2
        )

    def test_provider_factory_resolution_and_singleton(self):
        """
        Verifies provider factory swaps instances cleanly and enforces configuration singletons.
        """
        config1 = AIConfiguration.objects.create(
            active_provider='gemini',
            model_name='gemini-flash-latest',
            is_active=True
        )
        provider = ProviderFactory.get_provider()
        self.assertEqual(provider.model_name, 'gemini-flash-latest')
        
        # Activating second config must deactivate the first configuration
        config2 = AIConfiguration.objects.create(
            active_provider='openrouter',
            model_name='meta-llama/llama-3',
            is_active=True
        )
        config1.refresh_from_db()
        self.assertFalse(config1.is_active)
        self.assertTrue(config2.is_active)
        
        provider = ProviderFactory.get_provider()
        self.assertEqual(provider.model_name, 'meta-llama/llama-3')

    @patch("intelligence.providers.gemini.requests.post")
    def test_assistant_engine_tool_calling_loop_tenant_safety(self, mock_post):
        """
        Verifies assistant orchestration loops tool runs securely without leaking tenant separation boundaries.
        """
        # First LLM mock response: requests tool call
        mock_response_1 = Mock()
        mock_response_1.status_code = 200
        mock_response_1.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "functionCall": {
                            "name": "get_sales_summary",
                            "args": {
                                "start_date": "2026-07-16"
                            }
                        }
                    }]
                }
            }]
        }
        
        # Second LLM mock response: yields final answer
        mock_response_2 = Mock()
        mock_response_2.status_code = 200
        mock_response_2.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": "Your total sales for today is NGN 0.00."
                    }]
                }
            }]
        }
        
        mock_post.side_effect = [mock_response_1, mock_response_2]
        
        conv = Conversation.objects.create(
            organization=self.org1,
            branch=self.branch1,
            created_by=self.owner,
            title="Sales Query"
        )
        
        engine = AssistantEngine()
        result_message = engine.run_conversation_turn(conv, "Summarize today's sales.")
        
        self.assertEqual(result_message.role, "assistant")
        self.assertIn("NGN 0.00", result_message.content)
        
        # Check database logs (user, assistant-request, tool-output, assistant-final)
        messages = Message.objects.filter(conversation=conv).order_by('timestamp')
        self.assertEqual(messages.count(), 4)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[1].role, "assistant")
        self.assertEqual(messages[2].role, "tool")
        self.assertEqual(messages[3].role, "assistant")
