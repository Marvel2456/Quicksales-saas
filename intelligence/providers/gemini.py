import requests
import json
import uuid
from typing import List, Iterator, Dict, Any, Optional
from .base import BaseProvider

class GeminiProvider(BaseProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-flash-latest"):
        self.api_key = api_key
        self.model_name = model_name
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

    def _convert_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        gemini_contents = []
        for msg in history:
            role = msg.get('role')
            content = msg.get('content')
            tool_calls = msg.get('tool_calls')
            name = msg.get('name')
            
            # Map roles
            if role == 'user':
                gemini_contents.append({
                    'role': 'user',
                    'parts': [{'text': content}]
                })
            elif role == 'assistant':
                parts = []
                if content:
                    parts.append({'text': content})
                if tool_calls:
                    for tc in tool_calls:
                        func_info = tc.get('function', {})
                        args = func_info.get('arguments', '{}')
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except:
                                args = {}
                        parts.append({
                            'functionCall': {
                                'name': func_info.get('name'),
                                'args': args
                            }
                        })
                # If both content and tool_calls are empty, avoid writing empty model block
                if parts:
                    gemini_contents.append({
                        'role': 'model',
                        'parts': parts
                    })
            elif role == 'tool':
                try:
                    response_json = json.loads(content)
                except:
                    response_json = {'result': content}
                
                if not isinstance(response_json, dict):
                    response_json = {'result': response_json}
                    
                gemini_contents.append({
                    'role': 'function',
                    'parts': [{
                        'functionResponse': {
                            'name': name,
                            'response': response_json
                        }
                    }]
                })
        return gemini_contents

    def _convert_tools(self, tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        if not tools:
            return None
        declarations = []
        for t in tools:
            func = t.get('function', {})
            declarations.append({
                'name': func.get('name'),
                'description': func.get('description'),
                'parameters': func.get('parameters')
            })
        return [{'functionDeclarations': declarations}]

    def generate_response(self, prompt: str, system_instruction: str, history: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        contents = self._convert_history(history)
        contents.append({
            'role': 'user',
            'parts': [{'text': prompt}]
        })
        
        payload = {
            'contents': contents,
        }
        if system_instruction:
            payload['systemInstruction'] = {
                'parts': [{'text': system_instruction}]
            }
        if tools:
            payload['tools'] = self._convert_tools(tools)

        headers = {'Content-Type': 'application/json'}
        response = requests.post(self.url, headers=headers, json=payload, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"Gemini API returned status {response.status_code}: {response.text}")
            
        res_json = response.json()
        
        candidate = res_json.get('candidates', [{}])[0]
        content_part = candidate.get('content', {})
        parts = content_part.get('parts', [])
        
        text_content = None
        tool_calls = None
        
        for part in parts:
            if 'text' in part:
                text_content = part['text']
            elif 'functionCall' in part:
                fc = part['functionCall']
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append({
                    'id': f"call_{uuid.uuid4().hex[:8]}",
                    'type': 'function',
                    'function': {
                        'name': fc.get('name'),
                        'arguments': json.dumps(fc.get('args', {}))
                    }
                })
                
        return {
            'text': text_content,
            'tool_calls': tool_calls,
            'raw_response': res_json
        }

    def generate_stream(self, prompt: str, system_instruction: str, history: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Iterator[Dict[str, Any]]:
        stream_url = self.url.replace("generateContent", "streamGenerateContent")
        contents = self._convert_history(history)
        contents.append({
            'role': 'user',
            'parts': [{'text': prompt}]
        })
        
        payload = {
            'contents': contents,
        }
        if system_instruction:
            payload['systemInstruction'] = {
                'parts': [{'text': system_instruction}]
            }
        if tools:
            payload['tools'] = self._convert_tools(tools)

        headers = {'Content-Type': 'application/json'}
        response = requests.post(stream_url, headers=headers, json=payload, stream=True, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"Gemini API returned status {response.status_code}: {response.text}")
            
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8').strip()
                if decoded_line.startswith('['):
                    decoded_line = decoded_line[1:]
                if decoded_line.endswith(','):
                    decoded_line = decoded_line[:-1]
                if decoded_line.endswith(']'):
                    decoded_line = decoded_line[:-1]
                
                if not decoded_line:
                    continue
                    
                try:
                    chunk_json = json.loads(decoded_line)
                    candidate = chunk_json.get('candidates', [{}])[0]
                    content_part = candidate.get('content', {})
                    parts = content_part.get('parts', [])
                    
                    text_content = None
                    tool_calls = None
                    
                    for part in parts:
                        if 'text' in part:
                            text_content = part['text']
                        elif 'functionCall' in part:
                            fc = part['functionCall']
                            if tool_calls is None:
                                tool_calls = []
                            tool_calls.append({
                                'id': f"call_{uuid.uuid4().hex[:8]}",
                                'type': 'function',
                                'function': {
                                    'name': fc.get('name'),
                                    'arguments': json.dumps(fc.get('args', {}))
                                }
                            })
                            
                    yield {
                        'text': text_content,
                        'tool_calls': tool_calls,
                        'raw_chunk': chunk_json
                    }
                except Exception:
                    pass
