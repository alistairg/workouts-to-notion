"""Rate limiting functionality for webhook requests."""

from datetime import datetime, timedelta
from collections import defaultdict

# Rate limiting configuration
MAX_REQUESTS_PER_MINUTE = 10
_request_counts = defaultdict(list)


def check_rate_limit(identifier):
    """
    Check if request should be rate limited.
    
    Args:
        identifier: IP address or user identifier
        
    Returns:
        tuple: (is_allowed, retry_after_seconds)
    """
    now = datetime.now()
    cutoff = now - timedelta(minutes=1)
    
    # Clean old entries
    _request_counts[identifier] = [
        req_time for req_time in _request_counts[identifier]
        if req_time > cutoff
    ]
    
    # Check limit
    if len(_request_counts[identifier]) >= MAX_REQUESTS_PER_MINUTE:
        oldest = min(_request_counts[identifier])
        retry_after = int((oldest + timedelta(minutes=1) - now).total_seconds())
        return False, retry_after
    
    # Add current request
    _request_counts[identifier].append(now)
    return True, 0
