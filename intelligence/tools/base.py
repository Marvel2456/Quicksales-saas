import abc
from typing import Dict, Any
from account.models import Organization, Branch

class BaseTool(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self) -> str:
        """
        Unique name of the tool, matching standard function naming (e.g. get_branch_sales).
        """
        pass

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """
        Clear, descriptive instruction for the LLM on when and how to call this tool.
        """
        pass

    @property
    @abc.abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """
        Returns JSONSchema defining the tool's expected arguments.
        """
        pass

    @abc.abstractmethod
    def execute(self, args: Dict[str, Any], organization: Organization, branch: Branch = None) -> Any:
        """
        Executes the business logic of the tool securely within active tenant parameters.
        """
        pass
