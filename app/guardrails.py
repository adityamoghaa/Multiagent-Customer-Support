"""
Guardrails module for the FastAPI customer support API.

NOTE: The PII redaction provided here is regex-based and is NOT production-grade.
It is intended for demonstration purposes only.
"""

import re
import threading
import time

try:
    from multiagent_support.tool_agent import BLOCKED_PATTERNS, input_guardrail
except ImportError:
    # Fallback if multiagent_support is not on sys.path
    BLOCKED_PATTERNS = [
        "ignore previous instructions", "system prompt", "rm -rf", "__import__"
    ]

    def input_guardrail(query: str) -> str | None:
        """Fallback: returns reason string if blocked, None if OK."""
        lowered = query.lower()
        for pattern in BLOCKED_PATTERNS:
            if pattern in lowered:
                return f"blocked pattern detected: '{pattern}'"
        if len(query) > 500:
            return "query exceeds max length guardrail"
        return None

# Additional harmful content keywords beyond what tool_agent covers
ADDITIONAL_BLOCKED_PATTERNS = [
    "hack this", "bypass security", "exploit vulnerability",
    "jailbreak", "delete all data",
]


def redact_pii(text: str) -> str:
    """
    Redact PII from the input text using regex patterns.
    """
    # SSN: xxx-xx-xxxx
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN_REDACTED]', text)
    
    # Credit Card: 4 groups of 4 digits, or 13-19 digit sequences
    text = re.sub(r'\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{13,19}\b', '[CC_REDACTED]', text)
    
    # Phone numbers: +1-xxx-xxx-xxxx, (xxx) xxx-xxxx, xxx-xxx-xxxx, 10+ digit sequences
    # Since CC is already redacted, we can safely match 10+ digits here
    phone_pattern = r'(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}|\b\d{10,}\b'
    text = re.sub(phone_pattern, '[PHONE_REDACTED]', text)
    
    # Email addresses
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    text = re.sub(email_pattern, '[EMAIL_REDACTED]', text)
    
    return text

def check_content_filter(query: str) -> str | None:
    """
    Check if the query contains blocked patterns or violates guardrails.

    Returns a reason string if blocked, None if the query is allowed.
    """
    # Use the existing input_guardrail from tool_agent (returns reason or None)
    guardrail_reason = input_guardrail(query)
    if guardrail_reason:
        return guardrail_reason

    # Check against additional blocked patterns
    query_lower = query.lower()
    for pattern in ADDITIONAL_BLOCKED_PATTERNS:
        if pattern in query_lower:
            return f"Content policy violation: '{pattern}'"

    return None

class RateLimiter:
    """
    In-memory rate limiter using a sliding window (token bucket approximation).
    """
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = {}
        self.lock = threading.Lock()
        
    def is_allowed(self, customer_id: str) -> bool:
        """
        Check if the request is allowed within the rate limit.
        """
        with self.lock:
            now = time.time()
            if customer_id not in self.requests:
                self.requests[customer_id] = []
                
            # Remove old requests
            self.requests[customer_id] = [
                req_time for req_time in self.requests[customer_id]
                if now - req_time < self.window_seconds
            ]
            
            if len(self.requests[customer_id]) < self.max_requests:
                self.requests[customer_id].append(now)
                return True
                
            return False
            
    def get_retry_after(self, customer_id: str) -> int:
        """
        Get the number of seconds until the next request is allowed.
        """
        with self.lock:
            if customer_id not in self.requests:
                return 0
                
            now = time.time()
            valid_requests = [
                req_time for req_time in self.requests[customer_id]
                if now - req_time < self.window_seconds
            ]
            
            if len(valid_requests) < self.max_requests:
                return 0
                
            oldest_request = valid_requests[0]
            retry_after = int(self.window_seconds - (now - oldest_request))
            return max(0, retry_after)
