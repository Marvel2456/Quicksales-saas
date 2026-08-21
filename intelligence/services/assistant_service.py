from typing import Iterator
from intelligence.core.assistant_engine import AssistantEngine
from intelligence.models import Conversation, Message

class AssistantService:
    def __init__(self):
        self.engine = AssistantEngine()

    def send_message(self, conversation: Conversation, prompt: str) -> Message:
        """
        Routes sync message turns.
        """
        return self.engine.run_conversation_turn(conversation, prompt)

    def stream_message(self, conversation: Conversation, prompt: str) -> Iterator[str]:
        """
        Routes streaming text turns.
        """
        return self.engine.run_conversation_turn_stream(conversation, prompt)
