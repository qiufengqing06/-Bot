"""
LLM Provider capability detection and configuration.
Handles provider-specific parameters to avoid cross-provider compatibility issues.
"""
from typing import Dict, Any, Optional
from nonebot.log import logger

from nonebot_agent.config import config


class LLMProviderCapabilities:
    """Provider-specific capability model for LLM API calls."""
    
    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        self.supports_repetition_penalty = False
        self.supports_thinking_control = False
        self.supports_seed = True
        self.supports_presence_penalty = True
        self.supports_frequency_penalty = True
        
        # Configure based on provider
        self._configure_provider()
    
    def _configure_provider(self):
        """Set capabilities based on provider name."""
        provider_lower = self.provider_name.lower()
        
        # DeepSeek supports repetition_penalty and thinking control
        if "deepseek" in provider_lower:
            self.supports_repetition_penalty = True
            self.supports_thinking_control = True
            logger.debug(f"[LLM] Detected DeepSeek provider, enabling repetition_penalty and thinking control")
        
        # OpenAI doesn't support repetition_penalty or thinking control
        elif "openai" in provider_lower or "gpt" in provider_lower:
            self.supports_repetition_penalty = False
            self.supports_thinking_control = False
            logger.debug(f"[LLM] Detected OpenAI provider")
        
        # Qwen/DashScope doesn't support repetition_penalty
        elif "qwen" in provider_lower or "dashscope" in provider_lower:
            self.supports_repetition_penalty = False
            self.supports_thinking_control = False
            logger.debug(f"[LLM] Detected Qwen/DashScope provider")
        
        # Anthropic/Claude
        elif "anthropic" in provider_lower or "claude" in provider_lower:
            self.supports_repetition_penalty = False
            self.supports_thinking_control = False
            logger.debug(f"[LLM] Detected Anthropic/Claude provider")
        
        # Google Gemini
        elif "gemini" in provider_lower or "google" in provider_lower:
            self.supports_repetition_penalty = False
            self.supports_thinking_control = False
            logger.debug(f"[LLM] Detected Gemini provider")
        
        # Default: conservative settings
        else:
            logger.debug(f"[LLM] Unknown provider '{self.provider_name}', using conservative settings")
    
    def build_extra_body(self) -> Optional[Dict[str, Any]]:
        """Build extra_body dict with only supported parameters."""
        extra_body = {}
        
        if self.supports_repetition_penalty:
            extra_body["repetition_penalty"] = 1.1
        
        if self.supports_thinking_control:
            extra_body["thinking"] = {"type": "disabled"}
        
        return extra_body if extra_body else None
    
    def build_call_params(self, base_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build complete API call parameters with provider-specific adjustments.
        
        Args:
            base_params: Base parameters (model, messages, temperature, etc.)
            
        Returns:
            Complete parameters dict with provider-specific additions
        """
        params = base_params.copy()
        
        # Remove seed if not supported (though most providers support it)
        if not self.supports_seed and "seed" in params:
            del params["seed"]
        
        # Add extra_body if we have provider-specific params
        extra_body = self.build_extra_body()
        if extra_body:
            params["extra_body"] = extra_body
        
        return params


def detect_provider() -> LLMProviderCapabilities:
    """
    Detect LLM provider from configuration.
    
    Detection priority:
    1. LLM_PROVIDER env var (if set)
    2. Infer from LLM_API_URL base URL patterns
    3. Default to "unknown"
    
    Returns:
        LLMProviderCapabilities instance
    """
    import os
    
    # Check explicit provider setting
    provider_name = os.getenv("LLM_PROVIDER", "").strip()
    
    if not provider_name:
        # Infer from API URL
        api_url = config.LLM_API_URL.lower()
        
        if "deepseek" in api_url:
            provider_name = "deepseek"
        elif "openai" in api_url:
            provider_name = "openai"
        elif "dashscope" in api_url or "qwen" in api_url:
            provider_name = "qwen"
        elif "anthropic" in api_url or "claude" in api_url:
            provider_name = "anthropic"
        elif "gemini" in api_url or "google" in api_url:
            provider_name = "gemini"
        else:
            provider_name = "unknown"
        
        logger.info(f"[LLM] Detected provider from URL: {provider_name}")
    else:
        logger.info(f"[LLM] Using explicit provider: {provider_name}")
    
    return LLMProviderCapabilities(provider_name)


# Global provider instance (initialized once)
_provider: Optional[LLMProviderCapabilities] = None


def get_provider() -> LLMProviderCapabilities:
    """Get the global provider capabilities instance."""
    global _provider
    if _provider is None:
        _provider = detect_provider()
    return _provider
