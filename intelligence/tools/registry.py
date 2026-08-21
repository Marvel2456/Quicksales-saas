from typing import Dict, Any, List
from .base import BaseTool
from .sales import GetSalesSummaryTool, GetTopProductsTool
from .inventory import GetInventorySummaryTool, GetStockAuditTrailTool
from .branch import GetBranchDetailsTool
from account.models import Organization, Branch

class ToolRegistry:
    # Instantiate and register all active tools
    _tools: Dict[str, BaseTool] = {
        "get_sales_summary": GetSalesSummaryTool(),
        "get_top_selling_products": GetTopProductsTool(),
        "get_inventory_summary": GetInventorySummaryTool(),
        "get_stock_audit_trail": GetStockAuditTrailTool(),
        "get_branch_details": GetBranchDetailsTool(),
    }

    @classmethod
    def get_all_tool_definitions(cls) -> List[Dict[str, Any]]:
        """
        Returns list of function definitions in OpenAI format.
        """
        definitions = []
        for name, tool in cls._tools.items():
            definitions.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            })
        return definitions

    @classmethod
    def execute_tool(cls, tool_name: str, args: Dict[str, Any], organization: Organization, branch: Branch = None) -> Any:
        """
        Executes a registered tool securely, forcing tenant context constraints.
        """
        tool = cls._tools.get(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not found in registry."}
            
        try:
            # Multi-tenancy enforcement: execute only under target organization context
            return tool.execute(args, organization, branch)
        except Exception as e:
            return {"error": f"Execution failed for tool '{tool_name}': {str(e)}"}
