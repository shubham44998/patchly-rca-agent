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
        print(f"[TokenTracker] on_llm_start called. Prompts count: {len(prompts)}")
    
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
        print(f"\n[TokenTracker] on_llm_end called. Call count: {self.call_count}")
        print(f"[TokenTracker] Response type: {type(response)}")
        print(f"[TokenTracker] Has llm_output: {hasattr(response, 'llm_output')}")
        if hasattr(response, 'llm_output'):
            print(f"[TokenTracker] llm_output: {response.llm_output}")
        
        # Method 1: Check llm_output.token_usage (OpenAI, Azure)
        if response.llm_output and "token_usage" in response.llm_output:
            usage = response.llm_output["token_usage"]
            self.total_tokens += usage.get("total_tokens", 0)
            self.prompt_tokens += usage.get("prompt_tokens", 0)
            self.completion_tokens += usage.get("completion_tokens", 0)
            print(f"[TokenTracker] ✓ Method 1 - Found token usage: {usage}")
            return
        
        # Method 2: Check usage_metadata in generations (Gemini, Anthropic)
        if hasattr(response, 'generations') and response.generations:
            print(f"[TokenTracker] Checking generations... count: {len(response.generations)}")
            for gen_list in response.generations:
                print(f"[TokenTracker] Gen list length: {len(gen_list)}")
                for gen in gen_list:
                    print(f"[TokenTracker] Gen type: {type(gen)}")
                    print(f"[TokenTracker] Has message: {hasattr(gen, 'message')}")
                    if hasattr(gen, 'message'):
                        print(f"[TokenTracker] Message type: {type(gen.message)}")
                        print(f"[TokenTracker] Has usage_metadata: {hasattr(gen.message, 'usage_metadata')}")
                        if hasattr(gen.message, 'usage_metadata'):
                            metadata = gen.message.usage_metadata
                            print(f"[TokenTracker] usage_metadata: {metadata}")
                            total = getattr(metadata, 'total_tokens', 0)
                            input_tok = getattr(metadata, 'input_tokens', 0)
                            output_tok = getattr(metadata, 'output_tokens', 0)
                            
                            self.total_tokens += total
                            self.prompt_tokens += input_tok
                            self.completion_tokens += output_tok
                            print(f"[TokenTracker] ✓ Method 2 - Found token usage: total={total}, input={input_tok}, output={output_tok}")
                            return
        
        # Method 3: Check response_metadata (alternative format)
        if hasattr(response, 'generations') and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    if hasattr(gen, 'message') and hasattr(gen.message, 'response_metadata'):
                        metadata = gen.message.response_metadata
                        print(f"[TokenTracker] response_metadata: {metadata}")
                        if 'usage_metadata' in metadata:
                            usage = metadata['usage_metadata']
                            self.total_tokens += usage.get('total_tokens', 0)
                            self.prompt_tokens += usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0)
                            self.completion_tokens += usage.get('completion_tokens', 0) or usage.get('output_tokens', 0)
                            print(f"[TokenTracker] ✓ Method 3 - Found token usage: {usage}")
                            return
        
        # Method 4: Estimate tokens if not provided
        print("[TokenTracker] ⚠ No token usage found - estimating tokens")
        if self._current_prompts:
            for prompt in self._current_prompts:
                self.prompt_tokens += self._estimate_tokens(prompt)
        
        if hasattr(response, 'generations') and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    if hasattr(gen, 'text'):
                        self.completion_tokens += self._estimate_tokens(gen.text)
        
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        print(f"[TokenTracker] Estimated tokens: prompt={self.prompt_tokens}, completion={self.completion_tokens}, total={self.total_tokens}")
    
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
