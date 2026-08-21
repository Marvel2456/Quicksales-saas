from typing import List, Dict, Any, Optional
from intelligence.models import Message, Conversation

class MemoryManager:
    @staticmethod
    def get_history(conversation: Conversation, limit: int = 30) -> List[Dict[str, Any]]:
        """
        Retrieves recent messages for a conversation formatted for provider ingestion.
        """
        messages = Message.objects.filter(conversation=conversation).order_by('timestamp')
        
        # Pull history list
        history_list = []
        for msg in messages:
            msg_dict = {
                'role': msg.role,
                'content': msg.content,
            }
            if msg.tool_calls:
                msg_dict['tool_calls'] = msg.tool_calls
            if msg.name:
                msg_dict['name'] = msg.name
                
            history_list.append(msg_dict)
            
        # Return only the last N messages, but slide carefully
        if len(history_list) > limit:
            # Shift slice but try not to break trailing tool calls
            history_list = history_list[-limit:]
            
        return history_list

    @staticmethod
    def persist_message(conversation: Conversation, role: str, content: Optional[str] = None, tool_calls: Optional[list] = None, name: Optional[str] = None) -> Message:
        """
        Saves a message record to database.
        """
        return Message.objects.create(
            conversation=conversation,
            role=role,
            content=content,
            tool_calls=tool_calls,
            name=name
        )
