from typing import List
from intelligence.models import Conversation
from account.models import Organization, Branch, CustomUser

class ConversationService:
    @staticmethod
    def create_conversation(organization: Organization, branch: Branch = None, user: CustomUser = None, title: str = "New Conversation") -> Conversation:
        """
        Creates a new conversation container.
        """
        return Conversation.objects.create(
            organization=organization,
            branch=branch,
            created_by=user,
            title=title
        )

    @staticmethod
    def get_conversations(organization: Organization, branch: Branch = None) -> List[Conversation]:
        """
        Retrieves conversations scoped to organization/branch, keeping only the last 3 most recent ones.
        """
        qs = Conversation.objects.filter(organization=organization)
        if branch:
            qs = qs.filter(branch=branch)
        
        # Order by newest first
        qs = qs.order_by('-created_at')
        
        all_conversations = list(qs)
        if len(all_conversations) > 3:
            keep = all_conversations[:3]
            delete_ids = [c.id for c in all_conversations[3:]]
            Conversation.objects.filter(id__in=delete_ids).delete()
            return keep
            
        return all_conversations

    @staticmethod
    def delete_conversation(conversation_id: str, organization: Organization) -> bool:
        """
        Deletes conversation securely.
        """
        try:
            conversation = Conversation.objects.get(id=conversation_id, organization=organization)
            conversation.delete()
            return True
        except Conversation.DoesNotExist:
            return False
