"""
Debug script to test token tracking
"""
import sys
sys.path.insert(0, 'src')

from patchly_rca.agent import run_rca

# Test with a simple input
result = run_rca("Test alert: API is returning 500 errors", source_override="text_message")

print("\n=== RESULT ===")
print(f"Steps taken: {result['steps_taken']}")
print(f"Provider: {result['provider']}")
print(f"Token usage: {result.get('token_usage', 'NOT FOUND')}")
print("\n=== TOKEN USAGE DETAILS ===")
token_usage = result.get('token_usage', {})
print(f"Total tokens: {token_usage.get('total_tokens', 0)}")
print(f"Prompt tokens: {token_usage.get('prompt_tokens', 0)}")
print(f"Completion tokens: {token_usage.get('completion_tokens', 0)}")
print(f"LLM calls: {token_usage.get('llm_calls', 0)}")
