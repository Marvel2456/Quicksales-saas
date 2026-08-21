from typing import Dict, Any
from .base import BaseTool
from account.models import Organization, Branch

class GetBranchDetailsTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_branch_details"

    @property
    def description(self) -> str:
        return "Retrieves the list of active branches for the organization, including branch names and configurations."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {}
        }

    def execute(self, args: Dict[str, Any], organization: Organization, branch: Branch = None) -> Any:
        branches = Branch.objects.filter(organization=organization)
        return [
            {
                'id': str(b.id),
                'name': b.name,
                'phone': getattr(b, 'phone_number', ''),
                'email': getattr(b, 'email', '')
            }
            for b in branches
        ]
