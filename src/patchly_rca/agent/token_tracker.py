"""
agent/token_tracker.py — Token Usage Tracking

Tracks token consumption across LLM calls using LangChain callbacks.
"""

import logging
from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not available - token estimation will be disabled")


class TokenTracker(BaseCallbackHandler):
    """Callback handler to track token usage across LLM calls."""
    
    def __init__(self):
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.call_count = 0
        self._current_prompts = []
    
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        """Store prompts for potential estimation."""
        self._current_prompts = prompts
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count using tiktoken or simple approximation."""
        if TIKTOKEN_AVAILABLE:
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
                return len(encoding.encode(text))
            except Exception:
                pass
        # Fallback: rough approximation (1 token ≈ 4 characters)
        return len(text) // 4
    
    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Called when LLM finishes running."""
        self.call_count += 1
        
        # Method 1: Check llm_output.token_usage (OpenAI, Azure)
        if response.llm_output and "token_usage" in response.llm_output:
            usage = response.llm_output["token_usage"]
            self.total_tokens += usage.get("total_tokens", 0)
            self.prompt_tokens += usage.get("prompt_tokens", 0)
            self.completion_tokens += usage.get("completion_tokens", 0)
            logger.debug(f"Token usage from llm_output: {usage}")
            return
        
        # Method 2: Check usage_metadata in generations (Gemini, Anthropic)
        if hasattr(response, 'generations') and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    if hasattr(gen, 'message') and hasattr(gen.message, 'usage_metadata'):
                        metadata = gen.message.usage_metadata
                        total = getattr(metadata, 'total_tokens', 0)
                        input_tok = getattr(metadata, 'input_tokens', 0)
                        output_tok = getattr(metadata, 'output_tokens', 0)
                        
                        self.total_tokens += total
                        self.prompt_tokens += input_tok
                        self.completion_tokens += output_tok
                        logger.debug(f"Token usage from usage_metadata: total={total}, input={input_tok}, output={output_tok}")
                        return
        
        # Method 3: Check response_metadata (alternative format)
        if hasattr(response, 'generations') and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    if hasattr(gen, 'message') and hasattr(gen.message, 'response_metadata'):
                        metadata = gen.message.response_metadata
                        if 'usage_metadata' in metadata:
                            usage = metadata['usage_metadata']
                            self.total_tokens += usage.get('total_tokens', 0)
                            self.prompt_tokens += usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0)
                            self.completion_tokens += usage.get('completion_tokens', 0) or usage.get('output_tokens', 0)
                            logger.debug(f"Token usage from response_metadata: {usage}")
                            return
        
        # Method 4: Estimate tokens if not provided
        logger.warning("No token usage found in LLM response - estimating tokens")
        if self._current_prompts:
            for prompt in self._current_prompts:
                self.prompt_tokens += self._estimate_tokens(prompt)
        
        if hasattr(response, 'generations') and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    if hasattr(gen, 'text'):
                        self.completion_tokens += self._estimate_tokens(gen.text)
        
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        logger.debug(f"Estimated tokens: prompt={self.prompt_tokens}, completion={self.completion_tokens}")
    
    def get_usage(self) -> Dict[str, int]:
        """Return current token usage statistics."""
        usage = {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "llm_calls": self.call_count,
            "estimated": self.total_tokens > 0 and self.call_count > 0,
        }
        print(f"\n[TokenTracker] Returning usage: {usage}\n")
        return usage
    
    def reset(self) -> None:
        """Reset all counters."""
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.call_count = 0
