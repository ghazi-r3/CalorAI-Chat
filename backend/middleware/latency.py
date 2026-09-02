"""
Latency tracking middleware for FastAPI.

Measures and reports p50 and p95 response times for both text and image paths.
The PDF requires these measurements with honest trade-off reasoning.
"""

import time
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass
class LatencyTracker:
    """
    Tracks response latencies and computes percentile statistics.

    Separates text-only requests from image requests so we can report
    p50/p95 independently as required.
    """
    text_latencies: list[float] = field(default_factory=list)
    image_latencies: list[float] = field(default_factory=list)

    def record(self, latency_ms: float, has_image: bool = False):
        """Record a request latency in milliseconds."""
        if has_image:
            self.image_latencies.append(latency_ms)
        else:
            self.text_latencies.append(latency_ms)

    def get_stats(self, path_type: str = "text") -> dict:
        """Compute p50 and p95 for the given path type."""
        latencies = self.text_latencies if path_type == "text" else self.image_latencies

        if not latencies:
            return {
                "path_type": path_type,
                "count": 0,
                "p50_ms": 0,
                "p95_ms": 0,
                "min_ms": 0,
                "max_ms": 0,
                "mean_ms": 0,
            }

        sorted_lats = sorted(latencies)
        n = len(sorted_lats)

        return {
            "path_type": path_type,
            "count": n,
            "p50_ms": round(sorted_lats[int(n * 0.50)] if n > 0 else 0, 1),
            "p95_ms": round(sorted_lats[int(n * 0.95)] if n > 0 else 0, 1),
            "min_ms": round(sorted_lats[0], 1),
            "max_ms": round(sorted_lats[-1], 1),
            "mean_ms": round(statistics.mean(sorted_lats), 1),
        }

    def get_all_stats(self) -> dict:
        """Get stats for both text and image paths."""
        return {
            "text": self.get_stats("text"),
            "image": self.get_stats("image"),
        }

    def reset(self):
        """Clear all recorded latencies."""
        self.text_latencies.clear()
        self.image_latencies.clear()


# Global tracker instance
latency_tracker = LatencyTracker()


class LatencyMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that records per-request latency.

    Adds an X-Response-Time-Ms header to every response.
    """

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        latency_ms = (time.time() - start) * 1000

        response.headers["X-Response-Time-Ms"] = f"{latency_ms:.1f}"
        return response
