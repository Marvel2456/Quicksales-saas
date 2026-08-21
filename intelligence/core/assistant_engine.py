import json
from typing import Dict, Any, List, Iterator, Optional
from intelligence.core.provider_factory import ProviderFactory
from intelligence.core.memory import MemoryManager
from intelligence.models import Conversation, Message
from intelligence.tools.registry import ToolRegistry
from intelligence.prompts.manager import PromptManager

class AssistantEngine:
    def __init__(self):
        self.provider = ProviderFactory.get_provider()

    def run_conversation_turn(self, conversation: Conversation, prompt: str) -> Message:
        """
        Runs a synchronous conversation turn. Supports multi-turn tool calling loops.
        """
        # Save user message
        MemoryManager.persist_message(conversation, role='user', content=prompt)

        # Dialogue loop to handle sequential tool calls
        loop_count = 0
        max_loops = 5
        
        while loop_count < max_loops:
            history = MemoryManager.get_history(conversation)
            system_instruction = PromptManager.get_system_prompt(conversation)
            tools_list = ToolRegistry.get_all_tool_definitions()

            response = self.provider.generate_response(
                prompt="",  # Context already injected in history
                system_instruction=system_instruction,
                history=history,
                tools=tools_list
            )

            text = response.get('text')
            tool_calls = response.get('tool_calls')

            if tool_calls:
                # 1. Save assistant request containing tool calls
                MemoryManager.persist_message(
                    conversation, 
                    role='assistant', 
                    content=text, 
                    tool_calls=tool_calls
                )

                # 2. Run tools
                for tc in tool_calls:
                    func_info = tc.get('function', {})
                    tool_name = func_info.get('name')
                    raw_args = func_info.get('arguments', '{}')
                    
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except:
                        args = {}

                    # Enforce tenant separation by forcing organization/branch arguments
                    result = ToolRegistry.execute_tool(
                        tool_name=tool_name,
                        args=args,
                        organization=conversation.organization,
                        branch=conversation.branch
                    )

                    # 3. Save tool output as a separate message
                    MemoryManager.persist_message(
                        conversation,
                        role='tool',
                        content=json.dumps(result),
                        name=tool_name
                    )

                loop_count += 1
                continue
            else:
                # No more tools, return assistant text
                return MemoryManager.persist_message(conversation, role='assistant', content=text)

        raise Exception("Max tool execution depth exceeded.")

    def run_conversation_turn_stream(self, conversation: Conversation, prompt: str) -> Iterator[str]:
        """
        Streams conversation response text delta-by-delta. Resolves tool call loops in the background.
        """
        # Save user message
        MemoryManager.persist_message(conversation, role='user', content=prompt)
        
        loop_count = 0
        max_loops = 5
        
        while loop_count < max_loops:
            history = MemoryManager.get_history(conversation)
            system_instruction = PromptManager.get_system_prompt(conversation)
            tools_list = ToolRegistry.get_all_tool_definitions()

            # Call provider synchronously to check if it wants to invoke any tools first
            response = self.provider.generate_response(
                prompt="",
                system_instruction=system_instruction,
                history=history,
                tools=tools_list
            )

            text = response.get('text')
            tool_calls = response.get('tool_calls')

            if tool_calls:
                # Save assistant tool call request
                MemoryManager.persist_message(
                    conversation, 
                    role='assistant', 
                    content=text, 
                    tool_calls=tool_calls
                )

                for tc in tool_calls:
                    func_info = tc.get('function', {})
                    tool_name = func_info.get('name')
                    raw_args = func_info.get('arguments', '{}')
                    
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except:
                        args = {}

                    result = ToolRegistry.execute_tool(
                        tool_name=tool_name,
                        args=args,
                        organization=conversation.organization,
                        branch=conversation.branch
                    )

                    MemoryManager.persist_message(
                        conversation,
                        role='tool',
                        content=json.dumps(result),
                        name=tool_name
                    )

                loop_count += 1
                continue
            else:
                # Stream the final text response
                stream = self.provider.generate_stream(
                    prompt="",
                    system_instruction=system_instruction,
                    history=history
                )
                
                full_text = []
                for chunk in stream:
                    chunk_text = chunk.get('text')
                    if chunk_text:
                        full_text.append(chunk_text)
                        yield chunk_text

                # Save complete aggregated assistant response
                if full_text:
                    MemoryManager.persist_message(
                        conversation, 
                        role='assistant', 
                        content="".join(full_text)
                    )
                return

        raise Exception("Max tool execution depth exceeded.")
