from django.conf import settings
from decouple import config
from intelligence.models import AIConfiguration
from intelligence.providers.gemini import GeminiProvider
from intelligence.providers.openrouter import OpenRouterProvider
from intelligence.providers.local import LocalProvider

class ProviderFactory:
    @staticmethod
    def get_provider():
        # Try to retrieve from database dynamic config
        db_config = AIConfiguration.get_active()
        if db_config:
            provider_type = db_config.active_provider
            model_name = db_config.model_name
        else:
            # Fall back to settings / environment variables
            provider_type = config("AI_PROVIDER", default="gemini")
            model_name = config("AI_MODEL_NAME", default="gemini-flash-latest")

        # Resolve keys
        gemini_key = config("GEMINI_API_KEY", default="")
        openrouter_key = config("OPENROUTER_API_KEY", default="")
        local_url = config("LOCAL_API_URL", default="http://localhost:11434/v1")

        if provider_type == 'gemini':
            return GeminiProvider(api_key=gemini_key, model_name=model_name)
        elif provider_type == 'openrouter':
            return OpenRouterProvider(api_key=openrouter_key, model_name=model_name)
        elif provider_type == 'local':
            return LocalProvider(api_url=local_url, model_name=model_name)
        else:
            return GeminiProvider(api_key=gemini_key, model_name=model_name)
