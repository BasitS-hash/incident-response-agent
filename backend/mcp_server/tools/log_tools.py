"""Mock log and metrics tools — replace with real log aggregator (Splunk, Loki, etc.)."""


def query_system_logs(service: str, minutes: int = 30) -> list[str]:
    return [
        f"[ERROR] {service}: connection timeout after 30s (x47 in last {minutes}m)",
        f"[ERROR] {service}: upstream connect error or disconnect/reset before headers",
        f"[WARN]  {service}: connection pool utilization at 98%",
        f"[ERROR] {service}: FATAL: remaining connection slots reserved for non-replication superuser",
        f"[INFO]  {service}: health check failed — pod restarting",
    ]


def get_system_metrics(service: str) -> dict:
    return {
        "service": service,
        "cpu_percent": 87,
        "memory_percent": 91,
        "active_connections": 498,
        "max_connections": 500,
        "error_rate_percent": 34.2,
        "p99_latency_ms": 4800,
        "pod_restarts_last_hour": 6,
    }


def get_deployment_history(service: str) -> list[dict]:
    return [
        {
            "deployed_at": "2025-05-22T13:55:00Z",
            "version": "v2.4.1",
            "changed_by": "ci-pipeline",
            "change": "Increased default thread pool size from 50 to 200",
        },
        {
            "deployed_at": "2025-05-22T10:00:00Z",
            "version": "v2.4.0",
            "changed_by": "john.smith",
            "change": "Updated ORM connection settings",
        },
    ]
