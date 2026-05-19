# Token Usage Implementation - Summary

## What Has Been Implemented

### 1. Token Tracker (`src/patchly_rca/agent/token_tracker.py`)
- Tracks tokens from LLM responses using multiple methods:
  - Method 1: `llm_output.token_usage` (OpenAI, Azure)
  - Method 2: `usage_metadata` in generations (Gemini, Anthropic)
  - Method 3: `response_metadata.usage_metadata` (alternative format)
  - Method 4: Token estimation fallback using tiktoken or approximation

### 2. RCA Agent Integration (`src/patchly_rca/agent/rca_agent.py`)
- TokenTracker callback attached to agent invocations
- Returns token usage in response dictionary

### 3. API Endpoints (`src/patchly_rca/api/main.py`)
- Added `token_usage` field to AnalyzeResponse model
- All endpoints return token statistics:
  ```json
  {
    "rca_report": "...",
    "steps_taken": 3,
    "provider": "gemini/gemini-2.5-flash",
    "token_usage": {
      "total_tokens": 1234,
      "prompt_tokens": 856,
      "completion_tokens": 378,
      "llm_calls": 3,
      "estimated": false
    }
  }
  ```

### 4. CLI Display (`main.py`)
Shows token usage after each investigation:
```
Steps taken : 3
LLM         : gemini/gemini-2.5-flash
Tokens      : 1,234 total (856 prompt + 378 completion)
LLM calls   : 3
```

### 5. Streamlit UI (`ui/app.py`)
Displays token usage in two places:

**Metrics Row:**
- Steps Taken | LLM Provider | Timestamp | **Total Tokens**

**Caption Below:**
- 🔢 Token Usage: 856 prompt + 378 completion = 1,234 total (3 LLM calls)
- Shows "(estimated)" note if tokens were estimated rather than from LLM

## How to See Token Usage on UI

1. **Start the servers:**
   ```bash
   python main.py both
   ```

2. **Open UI:** http://localhost:8501

3. **Run an RCA investigation** with any input (text alert, log file, etc.)

4. **After completion, you'll see:**
   - 4th metric column showing "Total Tokens: 1,234"
   - Caption below showing detailed breakdown
   - If tokens = 0, it shows "N/A" in the metric

## Troubleshooting

### If you don't see token usage:

1. **Check the browser console** (F12) for any errors

2. **Check API response** by calling directly:
   ```bash
   curl -X POST http://localhost:8000/analyze \
     -H "Content-Type: application/json" \
     -d '{"input": "test alert", "source": "text_message"}'
   ```
   Look for `token_usage` in the response

3. **Check server logs** - you should see:
   ```
   [TokenTracker] Returning usage: {'total_tokens': 1234, ...}
   ```

4. **Gemini Rate Limits:** If you hit rate limits, wait or switch to another provider

### Debug Mode

To see detailed token tracking logs, the code now includes:
- Debug prints in TokenTracker.get_usage()
- Warning logs when tokens aren't found in LLM response
- Automatic fallback to token estimation

## Provider Support

- ✅ **OpenAI**: Full support (native token usage)
- ✅ **Azure OpenAI**: Full support (native token usage)
- ✅ **Anthropic**: Full support (usage_metadata)
- ✅ **Google Gemini**: Full support (usage_metadata)
- ⚠️ **Ollama**: Estimated tokens (most models don't return usage)

## Next Steps

Once you run an investigation through the UI, you should see the token usage displayed. If you still don't see it:

1. Check the terminal where you ran `python main.py both` for the debug print
2. Share the API response or error message
3. Verify which LLM provider you're using
