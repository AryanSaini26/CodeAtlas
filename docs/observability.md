# Observability

The HTTP server exposes Prometheus metrics at **`/metrics`** (no auth — scrape it
from inside your network or behind the reverse proxy). Metrics are emitted only
when `prometheus-client` is installed (it ships with the `api` extra); otherwise
`/metrics` returns `503` and the app runs unaffected.

## Metrics

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `codeatlas_http_requests_total` | counter | `prefix`, `method`, `status` | HTTP requests by coarse route prefix |
| `codeatlas_http_request_duration_seconds` | histogram | `prefix` | Request latency |
| `codeatlas_sync_jobs_total` | counter | `status` | Hosted sync jobs by terminal status |

The `prefix` label is intentionally coarse (`/api/v1`, `/api/hosted/v1`,
`/health`, `/metrics`, `other`) to keep cardinality bounded.

## Scrape config

```yaml
scrape_configs:
  - job_name: stratum
    static_configs:
      - targets: ["stratum.duckdns.org:443"]
    scheme: https
    metrics_path: /metrics
```

## Grafana

Import `deploy/grafana/stratum-dashboard.json` and select your Prometheus data
source. Panels: request rate by prefix, p95 latency, 5xx error rate, and sync
jobs by status.

Tracing: `codeatlas.observability.trace_span` emits OpenTelemetry spans when
`opentelemetry-api` is present (the `observability` extra), and is a no-op
otherwise.
