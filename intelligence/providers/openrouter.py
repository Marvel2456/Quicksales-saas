import requests
import json
from typing import List, Iterator, Dict, Any, Optional
from .base import BaseProvider

class OpenRouterProvider(BaseProvider):
    def __init__(self, api_key: str, model_name: str = "google/gemini-flash-latest"):
        self.api_key = api_key
        self.model_name = model_name
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    def _convert_messages(self, prompt: str, system_instruction: str, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        messages = []
        if system_instruction:
            messages.append({
                'role': 'system',
                'content': system_instruction
            })
            
        for msg in history:
            role = msg.get('role')
            content = msg.get('content')
            tool_calls = msg.get('tool_calls')
            name = msg.get('name')
            
            message_obj = {
                'role': role,
            }
            if content is not None:
                message_obj['content'] = content
            if tool_calls:
                message_obj['tool_calls'] = tool_calls
            if name:
                message_obj['name'] = name
                
            if role == 'tool':
                message_obj['tool_call_id'] = msg.get('tool_call_id') or msg.get('name') or 'call_id'
                
            messages.append(message_obj)
            
        messages.append({
            'role': 'user',
            'content': prompt
        })
        return messages

    def generate_response(self, prompt: str, system_instruction: str, history: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        messages = self._convert_messages(prompt, system_instruction, history)
        payload = {
            'model': self.model_name,
            'messages': messages
        }
        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = 'auto'

        headers = {
            'Authorization': f"Bearer {self.api_key}",
            'Content-Type': 'application/json',
            'HTTP-Referer': 'http://marvexqs.com',
            'X-Title': 'MarvexQS Intelligence'
        }
        
        response = requests.post(self.url, headers=headers, json=payload, timeout=10)
        if response.status_code != 200:
            raise Exception(f"OpenRouter API returned status {response.status_code}: {response.text}")
            
        res_json = response.json()
        choice = res_json.get('choices', [{}])[0]
        message = choice.get('message', {})
        
        return {
            'text': message.get('content'),
            'tool_calls': message.get('tool_calls'),
            'raw_response': res_json
        }

    def generate_stream(self, prompt: str, system_instruction: str, history: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Iterator[Dict[str, Any]]:
        messages = self._convert_messages(prompt, system_instruction, history)
        payload = {
            'model': self.model_name,
            'messages': messages,
            'stream': True
        }
        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = 'auto'

        headers = {
            'Authorization': f"Bearer {self.api_key}",
            'Content-Type': 'application/json',
            'HTTP-Referer': 'http://marvexqs.com',
            'X-Title': 'MarvexQS Intelligence'
        }
        
        response = requests.post(self.url, headers=headers, json=payload, stream=True, timeout=10)
        if response.status_code != 200:
            raise Exception(f"OpenRouter API returned status {response.status_code}: {response.text}")
            
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8').strip()
                if decoded_line.startswith("data: "):
                    data_str = decoded_line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(data_str)
                        choice = chunk_json.get('choices', [{}])[0]
                        delta = choice.get('delta', {})
                        yield {
                            'text': delta.get('content'),
                            'tool_calls': delta.get('tool_calls'),
                            'raw_chunk': chunk_json
                        }
                    except Exception:
                        pass
