"""
tools/stack_trace_analyzer.py — Extract detailed context from stack traces
"""

import re
import json
import os
import yaml
from typing import Dict, List
from langchain_core.tools import tool


# Load project context configuration
def _load_project_context():
    config_path = os.path.join(os.path.dirname(__file__), "../../project_context.yml")
    try:
        if os.path.exists(config_path):
            with open(config_path) as f:
                return yaml.safe_load(f)
    except Exception:
        pass
    return {"application_packages": ["com.vinay", "com.example", "org.company"]}

PROJECT_CONTEXT = _load_project_context()


@tool
def analyze_stack_trace(input_text: str) -> str:
    """
    Analyze Java/Python stack traces to extract:
    - Exception type and message
    - Exact file, class, method, and line numbers
    - Root cause location (first occurrence in application code)
    
    Use this when you see stack traces in error logs or incident payloads.
    Returns structured analysis with specific file locations.
    """
    
    # Java stack trace pattern: at com.example.Service.method(File.java:123)
    java_pattern = r'at\s+([\w\.]+)\(([\w\.]+):(\d+)\)'
    
    # Python stack trace pattern: File "path/file.py", line 123, in method
    python_pattern = r'File\s+"([^"]+)",\s+line\s+(\d+),\s+in\s+(\w+)'
    
    java_matches = re.findall(java_pattern, input_text)
    python_matches = re.findall(python_pattern, input_text)
    
    # Extract exception type
    exception_patterns = [
        r'(\w+Exception):\s*(.+)',
        r'(\w+Error):\s*(.+)',
        r'Exception in thread.*?\s+(\w+):\s*(.+)'
    ]
    
    exception_info = None
    for pattern in exception_patterns:
        match = re.search(pattern, input_text)
        if match:
            exception_info = {"type": match.group(1), "message": match.group(2).strip()}
            break
    
    result = {
        "exception": exception_info or {"type": "Unknown", "message": "No exception found"},
        "stack_frames": [],
        "root_cause_location": None
    }
    
    # Process Java stack traces
    app_packages = PROJECT_CONTEXT.get("application_packages", ["com.vinay", "com.example"])
    for full_method, filename, line_num in java_matches:
        parts = full_method.rsplit('.', 1)
        class_name = parts[0] if len(parts) > 1 else full_method
        method_name = parts[1] if len(parts) > 1 else ""
        
        frame = {
            "type": "java",
            "class": class_name,
            "method": method_name,
            "file": filename,
            "line": int(line_num),
            "is_application_code": any(class_name.startswith(pkg) for pkg in app_packages)
        }
        result["stack_frames"].append(frame)
        
        # First application code frame is usually root cause
        if not result["root_cause_location"] and frame["is_application_code"]:
            result["root_cause_location"] = frame
    
    # Process Python stack traces
    for filepath, line_num, func_name in python_matches:
        frame = {
            "type": "python",
            "file": filepath,
            "line": int(line_num),
            "function": func_name,
            "is_application_code": not any(x in filepath for x in ["site-packages", "lib/python"])
        }
        result["stack_frames"].append(frame)
        
        if not result["root_cause_location"] and frame["is_application_code"]:
            result["root_cause_location"] = frame
    
    # Format output
    output_lines = [
        f"EXCEPTION: {result['exception']['type']} - {result['exception']['message']}",
        f"",
        f"STACK FRAMES FOUND: {len(result['stack_frames'])}",
    ]
    
    if result["root_cause_location"]:
        loc = result["root_cause_location"]
        if loc.get("type") == "java":
            output_lines.append(f"")
            output_lines.append(f"ROOT CAUSE LOCATION:")
            output_lines.append(f"  Class:  {loc['class']}")
            output_lines.append(f"  Method: {loc['method']}")
            output_lines.append(f"  File:   {loc['file']}")
            output_lines.append(f"  Line:   {loc['line']}")
        else:
            output_lines.append(f"")
            output_lines.append(f"ROOT CAUSE LOCATION:")
            output_lines.append(f"  File:     {loc['file']}")
            output_lines.append(f"  Function: {loc['function']}")
            output_lines.append(f"  Line:     {loc['line']}")
    
    output_lines.append(f"")
    output_lines.append(f"APPLICATION CODE FRAMES:")
    for frame in result["stack_frames"]:
        if frame["is_application_code"]:
            if frame.get("type") == "java":
                output_lines.append(f"  • {frame['class']}.{frame['method']}() at {frame['file']}:{frame['line']}")
            else:
                output_lines.append(f"  • {frame['function']}() at {frame['file']}:{frame['line']}")
    
    return "\n".join(output_lines)


@tool
def extract_error_context(incident_payload: str) -> str:
    """
    Extract all error-related context from an incident payload including:
    - Service names, endpoints, methods
    - Error messages and types
    - Environment information
    - Timestamps
    
    Use this FIRST when analyzing an incident to understand what components are involved.
    """
    
    try:
        data = json.loads(incident_payload)
    except json.JSONDecodeError:
        # Try to extract from text
        return _extract_from_text(incident_payload)
    
    context = []
    
    # Service context
    if "service_name" in data or "service" in data:
        service = data.get("service_name") or data.get("service")
        context.append(f"SERVICE: {service}")
    
    if "method" in data:
        context.append(f"METHOD: {data['method']}")
    
    if "endpoint" in data or "path" in data:
        endpoint = data.get("endpoint") or data.get("path")
        context.append(f"ENDPOINT: {endpoint}")
    
    # Error details
    if "error_type" in data or "exception_type" in data:
        error_type = data.get("error_type") or data.get("exception_type")
        context.append(f"ERROR TYPE: {error_type}")
    
    if "error_message" in data or "message" in data:
        msg = data.get("error_message") or data.get("message")
        context.append(f"ERROR MESSAGE: {msg}")
    
    # Environment
    if "environment" in data:
        context.append(f"ENVIRONMENT: {data['environment']}")
    
    if "timestamp" in data:
        context.append(f"TIMESTAMP: {data['timestamp']}")
    
    # Project context if available
    if "project_context" in data:
        context.append(f"\nPROJECT CONTEXT:")
        for k, v in data["project_context"].items():
            context.append(f"  {k}: {v}")
    
    # Stack trace presence
    if "stack_trace" in data:
        context.append(f"\nSTACK TRACE: Available (use analyze_stack_trace tool)")
    
    return "\n".join(context) if context else "No structured error context found"


def _extract_from_text(text: str) -> str:
    """Extract context from plain text incident descriptions"""
    context = ["EXTRACTED FROM TEXT:"]
    
    # Look for common patterns
    if "exception" in text.lower() or "error" in text.lower():
        context.append("• Contains error/exception information")
    
    # Extract Java class references
    java_classes = re.findall(r'\b([A-Z][a-zA-Z0-9]*(?:\.[A-Z][a-zA-Z0-9]*)+)\b', text)
    if java_classes:
        context.append(f"• Java classes mentioned: {', '.join(set(java_classes[:5]))}")
    
    # Extract method calls
    method_calls = re.findall(r'\b(\w+)\(\)', text)
    if method_calls:
        context.append(f"• Methods mentioned: {', '.join(set(method_calls[:5]))}")
    
    return "\n".join(context)
