"""
agent/llm_factory.py — LLM Provider Factory
Compatible with: langchain==0.2.x, langchain-core==0.2.x, langchain-ollama==0.1.x

Returns a LangChain BaseChatModel from config.
"""

from langchain_core.language_models.chat_models import BaseChatModel


def get_llm(cfg: dict) -> BaseChatModel:
    provider = cfg["provider"].lower()

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=cfg.get("model", "llama3"),
            base_url=cfg.get("base_url", "http://localhost:11434"),
            temperature=cfg.get("temperature", 0.0),
            num_predict=cfg.get("max_tokens", 4096),
        )

    elif provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ImportError("Run: pip install langchain-openai")
        return ChatOpenAI(
            model=cfg.get("model", "gpt-4o"),
            api_key=cfg.get("api_key"),
            temperature=cfg.get("temperature", 0.0),
            max_tokens=cfg.get("max_tokens", 4096),
        )

    elif provider == "azure_openai":
        try:
            from langchain_openai import AzureChatOpenAI
        except ImportError:
            raise ImportError("Run: pip install langchain-openai")
        return AzureChatOpenAI(
            azure_deployment=cfg["deployment_name"],
            azure_endpoint=cfg["azure_endpoint"],
            api_key=cfg.get("azure_key", cfg.get("api_key", "")),
            api_version=cfg.get("api_version", "2024-02-01"),
            temperature=cfg.get("temperature", 0.0),
        )

    elif provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError("Run: pip install langchain-anthropic")
        return ChatAnthropic(
            model=cfg.get("model", "claude-3-5-sonnet-20241022"),
            api_key=cfg.get("anthropic_key", cfg.get("api_key", "")),
            temperature=cfg.get("temperature", 0.0),
            max_tokens=cfg.get("max_tokens", 4096),
        )

    elif provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise ImportError("Run: pip install langchain-google-genai")
        return ChatGoogleGenerativeAI(
            model=cfg.get("model", "gemini-1.5-pro"),
            google_api_key=cfg.get("gemini_key", ""),
            temperature=cfg.get("temperature", 0.0),
            max_output_tokens=cfg.get("max_tokens", 4096),
        )

    elif provider == "groq":
        try:
            from langchain_groq import ChatGroq
        except ImportError:
            raise ImportError("Run: pip install langchain-groq")
        return ChatGroq(
            model=cfg.get("model", "llama-3.3-70b-versatile"),
            groq_api_key=cfg.get("groq_key", cfg.get("api_key", "")),
            temperature=cfg.get("temperature", 0.0),
            max_tokens=cfg.get("max_tokens", 4096),
        )

    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. "
            "Options: ollama | openai | azure_openai | anthropic | gemini | groq"
        )
