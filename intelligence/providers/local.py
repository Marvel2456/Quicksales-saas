from .openrouter import OpenRouterProvider

class LocalProvider(OpenRouterProvider):
    def __init__(self, api_url: str = "http://localhost:11434/v1", model_name: str = "llama3"):
        # Local LLM engines like Ollama or vLLM run OpenAI compatibility on /chat/completions
        super().__init__(api_key="local-key", model_name=model_name)
        
        # Ensure we point to the local server URL
        base_url = api_url.rstrip('/')
        self.url = f"{base_url}/chat/completions"
