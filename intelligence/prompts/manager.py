from .system_prompts import ASSISTANT_SYSTEM_PROMPT
from intelligence.models import Conversation

class PromptManager:
    @staticmethod
    def get_system_prompt(conversation: Conversation) -> str:
        """
        Returns the assistant system prompt with active tenant context appended.
        """
        org_name = conversation.organization.name
        branch_name = conversation.branch.name if conversation.branch else "All Branches"
        
        user_role = "Staff"
        if conversation.created_by:
            # Safely fetch active role
            user_role = getattr(conversation.created_by, '_current_role', 'Staff')

        context_info = (
            f"\n\nActive Context Details:\n"
            f"- Organization: {org_name}\n"
            f"- Scoped Branch: {branch_name}\n"
            f"- User Role: {user_role}\n"
        )
        
        return f"{ASSISTANT_SYSTEM_PROMPT}{context_info}"
