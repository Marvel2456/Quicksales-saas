import abc
from typing import List, Iterator, Dict, Any, Optional

class BaseProvider(abc.ABC):
    @abc.abstractmethod
    def generate_response(
        self,
        prompt: str,
        system_instruction: str,
        history: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Executes a single synchronous LLM completion request.
        Returns a dict:
        {
            'text': str or None,
            'tool_calls': List[Dict[str, Any]] or None,
            'raw_response': Any
        }
        """
        pass

    @abc.abstractmethod
    def generate_stream(
        self,
        prompt: str,
        system_instruction: str,
        history: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Yields stream completion chunks.
        Each chunk is a dict:
        {
            'text': str or None,
            'tool_calls': List[Dict[str, Any]] or None,
            'raw_chunk': Any
        }
        """
        pass
