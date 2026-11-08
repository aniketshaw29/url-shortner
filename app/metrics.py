from prometheus_client import Counter, Gauge, Histogram

CACHE_OPERATIONS = Counter(
    "shortener_cache_operations_total",
    "Cache lookup results",
    ["result"],
)

REDIRECTS = Counter(
    "shortener_redirects_total",
    "Redirect outcomes",
    ["outcome"],
)

HTTP_REQUESTS = Counter(
    "shortener_http_requests_total",
    "HTTP requests by method, route template, and status",
    ["method", "route", "status"],
)

HTTP_DURATION = Histogram(
    "shortener_http_request_duration_seconds",
    "HTTP request latency by method and route template",
    ["method", "route"],
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

ANALYTICS_PENDING = Gauge(
    "shortener_analytics_stream_pending",
    "Pending analytics stream entries",
)

ANALYTICS_STREAM_LENGTH = Gauge(
    "shortener_analytics_stream_length",
    "Total analytics stream entries",
)

SQLITE_BUSY = Counter(
    "shortener_sqlite_busy_total",
    "SQLite database-is-locked errors",
)
