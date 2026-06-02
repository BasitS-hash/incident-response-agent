_LOG_DATA: dict[str, list[str]] = {
    "auth": [
        "[ERROR] auth-service: 503 Service Unavailable returned to client (x312 in last 30m)",
        "[ERROR] auth-service: upstream connect error — connection refused from token-validator",
        "[WARN]  auth-service: JWT validation latency p99=4200ms (threshold: 500ms)",
        "[ERROR] auth-service: Redis session cache MISS rate 97% — fallback to DB overwhelmed",
        "[ERROR] auth-service: pod CrashLoopBackOff — OOMKilled (limit: 512Mi, used: 509Mi)",
        "[INFO]  auth-service: horizontal pod autoscaler at max replicas (10/10)",
    ],
    "payment": [
        "[ERROR] payment-service: pq: sorry, too many clients already (connection 501/500)",
        "[ERROR] payment-service: context deadline exceeded — DB query timeout after 30s (x89 in last 30m)",
        "[ERROR] payment-service: checkout transaction rolled back — unable to acquire DB lock",
        "[WARN]  payment-service: connection pool exhausted — requests queuing (queue depth: 214)",
        "[ERROR] payment-service: FATAL: remaining connection slots reserved for superuser",
        "[INFO]  payment-service: pgBouncer pool_mode=session — all sessions occupied",
    ],
    "notification": [
        "[ERROR] notification-service: AWS SES SendEmail failed — Account suspended: bounce rate 12.4% exceeds 10% threshold",
        "[ERROR] notification-service: MessageRejected — Email address is on suppression list (x2341 in last 30m)",
        "[WARN]  notification-service: dead-letter queue depth 14,382 — consumer group falling behind",
        "[ERROR] notification-service: SQS batch processor failed — all 10 workers returning SES throttle errors",
        "[ERROR] notification-service: password-reset emails undelivered — queue TTL expiring for 890 messages",
        "[INFO]  notification-service: last successful SES send at 11:39 UTC — 6 minutes of full outage",
    ],
}

_METRICS_DATA: dict[str, dict] = {
    "auth": {
        "cpu_percent": 87,
        "memory_percent": 91,
        "active_connections": 498,
        "max_connections": 500,
        "error_rate_percent": 34.2,
        "p99_latency_ms": 4800,
        "pod_restarts_last_hour": 6,
        "cache_hit_rate_percent": 3,
    },
    "payment": {
        "cpu_percent": 42,
        "memory_percent": 61,
        "active_db_connections": 501,
        "max_db_connections": 500,
        "error_rate_percent": 78.5,
        "p99_latency_ms": 31200,
        "transactions_failed_last_30m": 1847,
        "pgbouncer_wait_queue_depth": 214,
    },
    "notification": {
        "cpu_percent": 18,
        "memory_percent": 34,
        "ses_bounce_rate_percent": 12.4,
        "ses_complaint_rate_percent": 0.6,
        "dlq_depth": 14382,
        "emails_sent_last_30m": 0,
        "emails_failed_last_30m": 2341,
        "worker_threads_active": 0,
        "queue_consumer_lag_seconds": 1840,
    },
}

_DEPLOYMENT_DATA: dict[str, list[dict]] = {
    "auth": [
        {
            "deployed_at": "2026-05-26T08:10:00Z",
            "version": "v3.1.2",
            "changed_by": "ci-pipeline",
            "change": "Reduced Redis connection pool size from 100 to 20 to cut costs",
        },
        {
            "deployed_at": "2026-05-25T14:00:00Z",
            "version": "v3.1.1",
            "changed_by": "alice.chen",
            "change": "Added new OAuth2 provider integration",
        },
    ],
    "payment": [
        {
            "deployed_at": "2026-05-26T07:45:00Z",
            "version": "v5.0.0",
            "changed_by": "bob.jones",
            "change": "Migrated ORM from SQLAlchemy to async Tortoise-ORM — connection pool config not ported",
        },
        {
            "deployed_at": "2026-05-25T18:30:00Z",
            "version": "v4.9.8",
            "changed_by": "ci-pipeline",
            "change": "Increased checkout worker threads from 20 to 80",
        },
    ],
    "notification": [
        {
            "deployed_at": "2026-05-26T11:30:00Z",
            "version": "v2.4.0",
            "changed_by": "priya.patel",
            "change": "Switched marketing email template engine — accidentally applied new unsubscribe logic to transactional emails, causing mass bounce classification",
        },
        {
            "deployed_at": "2026-05-25T16:00:00Z",
            "version": "v2.3.9",
            "changed_by": "ci-pipeline",
            "change": "Bumped SES SDK from v2 to v3 — default retry config changed",
        },
    ],
}

_DEFAULT_LOGS = [
    "[ERROR] {service}: connection timeout after 30s",
    "[ERROR] {service}: upstream connect error or disconnect/reset before headers",
    "[WARN]  {service}: connection pool utilization at 98%",
    "[ERROR] {service}: health check failed — pod restarting",
]

_DEFAULT_METRICS = {
    "cpu_percent": 75,
    "memory_percent": 80,
    "error_rate_percent": 25.0,
    "p99_latency_ms": 3000,
    "pod_restarts_last_hour": 3,
}

_DEFAULT_DEPLOYMENTS = [
    {
        "deployed_at": "2026-05-26T06:00:00Z",
        "version": "v1.0.1",
        "changed_by": "ci-pipeline",
        "change": "Dependency updates",
    }
]


def _service_key(service: str) -> str:
    s = service.lower()
    if "auth" in s:
        return "auth"
    if "payment" in s or "checkout" in s:
        return "payment"
    if "notif" in s or "email" in s or "ses" in s:
        return "notification"
    return ""


def query_system_logs(service: str, minutes: int = 30) -> list[str]:
    key = _service_key(service)
    if key:
        return _LOG_DATA[key]
    return [line.format(service=service) for line in _DEFAULT_LOGS]


def get_system_metrics(service: str) -> dict:
    key = _service_key(service)
    data = _METRICS_DATA.get(key, _DEFAULT_METRICS).copy()
    data["service"] = service
    return data


def get_deployment_history(service: str) -> list[dict]:
    key = _service_key(service)
    return _DEPLOYMENT_DATA.get(key, _DEFAULT_DEPLOYMENTS)
