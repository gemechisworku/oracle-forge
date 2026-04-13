"""Async rate limiter for Groq API calls to stay within free tier limits."""

import asyncio
import time
from typing import Optional
from collections import deque

class AsyncRateLimiter:
    """
    Token bucket rate limiter with configurable requests per minute.
    
    Features:
    - Burst handling
    - Queue for pending requests
    - Metrics for monitoring
    
    Usage:
        limiter = AsyncRateLimiter(requests_per_minute=30)
        await limiter.acquire()
        response = await groq_client.chat(...)
    """
    
    def __init__(self, requests_per_minute: float = 30.0, burst_size: Optional[int] = None):
        self.rate = requests_per_minute / 60.0  # tokens per second
        self.capacity = burst_size if burst_size else int(requests_per_minute)
        self.tokens = self.capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
        
        # Metrics
        self.total_requests = 0
        self.total_wait_time = 0.0
        self.queue_length = 0
        
    async def acquire(self) -> float:
        """
        Acquire a token, waiting if necessary.

        Returns:
            Wait time in seconds (0 if no wait)
        """
        async with self._lock:
            self.queue_length += 1
            now = time.monotonic()

            # Add tokens based on time elapsed
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= 1:
                self.tokens -= 1
                self.queue_length -= 1
                self.total_requests += 1
                return 0.0

            # Calculate wait time; set tokens to 0 before releasing lock
            wait_time = (1 - self.tokens) / self.rate
            self.tokens = 0

        # Lock is released here — other acquires can proceed during sleep
        await asyncio.sleep(wait_time)

        async with self._lock:
            self.last_update = time.monotonic()
            self.queue_length -= 1
            self.total_requests += 1
            self.total_wait_time += wait_time

        return wait_time
    
    def get_metrics(self) -> dict:
        """Return rate limiter performance metrics."""
        return {
            "total_requests": self.total_requests,
            "avg_wait_time_ms": (self.total_wait_time / max(1, self.total_requests)) * 1000,
            "current_queue": self.queue_length,
            "tokens_available": self.tokens,
            "capacity": self.capacity
        }
    
    async def __aenter__(self):
        await self.acquire()
        return self
    
    async def __aexit__(self, *args):
        pass