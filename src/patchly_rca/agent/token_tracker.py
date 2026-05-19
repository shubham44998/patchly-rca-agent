"""
agent/token_tracker.py — Token Usage Tracking

Tracks token consumption across LLM calls using LangChain callbacks.
"""

from typing import Any, Dict, List
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class TokenTracker(BaseCallbackHandler):
    """Callback handler to track token usage across LLM calls."""
    
    def __init__(self):
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.call_count = 0
    
    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Called when LLM finishes running."""
        if response.llm_output and "token_usage" in response.llm_output:
            usage = response.llm_output["token_usage"]
            self.total_tokens += usage.get("total_tokens", 0)
            self.prompt_tokens += usage.get("prompt_tokens", 0)
            self.completion_tokens += usage.get("completion_tokens", 0)
            self.call_count += 1
        # Handle usage_metadata (newer LangChain format)
        elif hasattr(response, 'generations') and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    if hasattr(gen, 'message') and hasattr(gen.message, 'usage_metadata'):
                        metadata = gen.message.usage_metadata
                        self.total_tokens += getattr(metadata, 'total_tokens', 0)
                        self.prompt_tokens += getattr(metadata, 'input_tokens', 0)
                        self.completion_tokens += getattr(metadata, 'output_tokens', 0)
                        self.call_count += 1
                        return
    
    def get_usage(self) -> Dict[str, int]:
        """Return current token usage statistics."""
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "llm_calls": self.call_count,
        }
    
    def reset(self) -> None:
        """Reset all counters."""
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.call_count = 0
