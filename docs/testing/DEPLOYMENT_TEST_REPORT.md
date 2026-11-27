# Docker and deployment verification

PASS: `Dockerfile.hosting` built as the separate local image
`careconnect-submission-test:local`. Image smoke evidence is `container_smoke.json`.
No existing infrastructure container was stopped/replaced; no public deployment
or DNS/TLS provisioning occurred.

Commands actually executed:

```powershell
docker build -f Dockerfile.hosting -t careconnect-submission-test:local .
.\.venv\Scripts\python.exe tools/check_container_image.py
docker compose -f docker-compose.yml config --no-interpolate --quiet
docker compose -f compose.hosting.yml config --no-interpolate --quiet
```

The image ran Gunicorn under UID/GID 10001 with a read-only root filesystem,
temporary /tmp, dropped capabilities and a random localhost-only host port.
HTTP checks passed for /health, /health/db, /services, /login and the active stylesheet;
/demo/request returned 404 in hosted mode. The database check/catalog rendering
made read-only queries to the existing MySQL instance through host.docker.internal.
No Admin credential was mounted, account session created or worker launched in
that image smoke. Its container was removed by its exact owned ID afterward.

The separate disposable integration runner tested the worker processes on genuine
MySQL/RabbitMQ and the Windows local supervisor. This is different from a complete
Linux Compose deployment. Hosted Compose has all five consumers, outbox and both
deadline scanners, durable data volumes, health checks, restart policies, secrets
mount and Caddy proxy. Schema preflight fails closed on an empty/unmigrated database;
the application never initializes it automatically.

Existing local Compose now obtains database/broker passwords from private environment
variables rather than committed defaults. It was validated without resolving secrets.
Future local service ports bind 127.0.0.1; existing all-interface bindings were not
changed. This edit does not change passwords in running containers. Existing containers can
continue running untouched; coordinated credential rotation remains manual.

NOT TESTED: complete hosted Compose launch, proxy certificates/public DNS, reboot
recovery, resource/load behavior, backup restoration and production Firebase domain
sign-in. No costs incurred or hosting purchased. Use [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md)
and the detailed [hosting runbook](../hosting/HOSTING_RUNBOOK.md) for the approved
provisioning sequence and remaining checks.



## Later owner verification — November 26, 2026

The owner confirmed the Azure deployment, HTTPS response, healthy endpoint, five active RabbitMQ consumers and successful login for all three demo roles. These are later owner-reported results, separate from the earlier image smoke test. Full hosted task evidence and actual inbox delivery were not supplied. A non-blocking Gunicorn read-only control-server warning remains for review.
