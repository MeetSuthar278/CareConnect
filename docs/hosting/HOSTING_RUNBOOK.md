# Hosting runbook

The configuration targets a single Linux VM with MySQL, RabbitMQ, Flask/Gunicorn,
and Caddy. All source paths required by `Dockerfile.hosting` are present, and
worker imports and Compose configuration checks pass. The final local image build,
Gunicorn/MySQL read-only smoke and disposable real MySQL/RabbitMQ worker tests passed.
The full Linux Compose stack, public DNS/TLS and production email flows remain untested.
Review the [deployment test report](../testing/DEPLOYMENT_TEST_REPORT.md) before
provisioning or launching. No public deployment is claimed.

## Configuration

- `compose.hosting.yml`: separate project `careconnect-hosted`, separate named volumes.
- `Dockerfile.hosting`: explicit runtime COPY paths, Linux Python, non-root UID 10001,
  Gunicorn. Local infrastructure uses `docker-compose.yml`.
- `requirements-hosting.txt`: original Python manifest plus Linux Gunicorn.
- `.dockerignore`: excludes environments, backups, review files, and private keys.
- `deploy/hosting.env.example`: placeholder-only private configuration template.
- `deploy/Caddyfile`: HTTPS proxy to private web:8000.
- `deploy/check_schema.py`: read-only schema and uniqueness/capacity preflight.
- `.gitignore`: also protects Firebase keys, deployment secrets and database backups.

Flask uses secure session cookies and trusts one proxy only in explicit HOSTED_MODE=1.
The web port has no host binding: only Caddy publishes 80/443. Never expose the app
directly while trusting forwarded headers. MySQL, RabbitMQ and management UI remain
on the Docker network without public ports. Hosted mode blocks legacy demo request
access even if testing/debug would otherwise allow it. Existing local behavior is kept.

## Configuration and build checks

Run in a terminal where Docker Desktop/Compose is available, from the project root:

```cmd
docker compose -f compose.hosting.yml config --no-interpolate --quiet
docker build -f Dockerfile.hosting -t careconnect-hosted:local .
```

The first validates Compose without printing private resolved environment values.
The second builds only an image; it does not start workers, import SQL or change the
current database. Configuration validation alone does not establish a working image or deployment.
Do not use `docker compose config` without quiet/no-interpolate with real secrets
when collecting screenshots or sharing logs.

## VM preparation

Use an x86-64 Ubuntu VM with adequate memory for MySQL, RabbitMQ and Python
processes. Review hosting, disk, public IP, and network costs before provisioning.
Deploy only the reviewed runtime repository files, not the Windows venv or backups.

Fill a private `deploy/.env.hosting` from `deploy/hosting.env.example` on the VM. Use
fresh independent secrets, not the local development credentials. Hexadecimal random
passwords simplify Compose and database-URL escaping. DATABASE_URL must use the same
database/user/password as MYSQL_* and the container hostname `mysql:3306`, not localhost
or Windows host port 3307. Broker traffic uses `rabbitmq:5672`, not host port 5673.

Keep the existing project's Firebase service account JSON outside the repository and
point FIREBASE_ADMIN_JSON at its absolute Linux path. Docker mounts it at runtime as
`/run/secrets/firebase_admin`, never copies it into the image. With bind-backed secrets,
ensure container UID 10001 can read that file; Compose permissions do not override
arbitrary host file permissions. Restrict the host file to that owner. Do not paste
the JSON/private key or populated env file into chat, git or screenshots.

Use `careconnect-bfb9e`; the frontend and backend both read FIREBASE_PROJECT_ID
and the public web variables from the environment. Add the eventual
website hostname to Firebase's authorized domains. Keep the VM's system clock
synchronized for token verification and deadline processing.

Point SITE_DOMAIN's DNS to the VM, permit HTTPS/HTTP for Caddy and restrict SSH to the
administrators' addresses. Caddy can obtain a public certificate only when that DNS
and inbound traffic work. Its data/config volumes retain certificates across restarts.

## Database provisioning and launch

Do not run baseline/reset scripts or migration 001 against the local or hosted database.
Choose a reviewed current synthetic export whose schema already includes approved
workflow/Firebase changes. Restore into the NEW hosted volume only after explicit
approval and after verifying target/project/database. No SQL is automatically mounted
under docker-entrypoint-initdb.d and the image contains no schema/seed/backup scripts.

After environment/schema verification and deployment review, run from the project root on the VM:

```sh
docker compose --env-file deploy/.env.hosting -f compose.hosting.yml build
docker compose --env-file deploy/.env.hosting -f compose.hosting.yml up -d mysql rabbitmq
```

Stop here until the exact export/restore operation is reviewed. On a fresh volume,
MySQL creates the configured empty database/user; it does not create application tables.
The preflight intentionally rejects this empty schema. It verifies required workflow
columns, Firebase UID uniqueness/nullable password hash, generated active-referral
slot/unique key, notification deduplication and the capacity check constraint.
It never repairs a schema or rewrites data.

After the approved restore, verify with:

```sh
docker compose --env-file deploy/.env.hosting -f compose.hosting.yml run --rm schema_check
```

Review imported requests/deadlines before the final start. The deadline commands
are configured with --apply; review their restored implementations for timeout and
overdue effects. Preserve existing requests' original SLA deadlines.

Only after schema, secrets, DNS, cost and deadline effects have been reviewed:

```sh
docker compose --env-file deploy/.env.hosting -f compose.hosting.yml up -d
docker compose --env-file deploy/.env.hosting -f compose.hosting.yml ps
docker compose --env-file deploy/.env.hosting -f compose.hosting.yml logs --tail 50 web matching notifications outbox
```

Compose requires topology setup and the read-only schema check before starting
web/workers/scanners. Services are configured to restart unless stopped; init forwards
shutdown signals. Named volumes retain MySQL/RabbitMQ data. Outbox recovery and
consumer retries are implemented; selected business delivery/replay paths passed
isolated network tests. Forced broker outage/restart still needs a separate exercise.
Back up the hosted DB to private storage separate from its VM disk and review restore
before executing it.
Never use `down -v`, delete volumes, or restore over an existing dataset without review.

## Completion checks and limits

After an actual launch: verify HTTPS login for all SQL roles, authorized Firebase
domain, private DB/broker ports, logs for all five consumers and outbox, both deadline
processes and persistent data after an approved restart. Verify a synthetic
request through matching and notification without resetting existing data.
Do not publish admin UIs or credentials to demonstrate queues; use controlled evidence.

Still unverified: live schema preflight, hosted MySQL/RabbitMQ and worker integration,
Gunicorn serving requests, HTTPS/DNS, container restart behavior and actual cloud/network/Firebase
integration. Existing MySQL8.0/RabbitMQ3.13 tags preserve project compatibility; evaluate
supported/patched versions before broader public use rather than silently upgrading
the database/broker here. This is a single-VM university demo, with no multi-host HA,
DLQ/bounded consumer retries or disaster-recovery guarantee.

Configuration references: [Flask proxy configuration](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/),
[Compose dependency conditions](https://docs.docker.com/compose/how-tos/startup-order/),
[Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https). These support the configuration design;
they do not establish a successful build or deployment of this project.


## Submission checks

Run `python tools/check_submission_readiness.py` for imports, template compilation,
source paths and project-ID consistency. With services running, explicitly add
`--database --rabbitmq` for read-only schema/mapping counts and passive topology
checks. Review verification email delivery and all SQL roles using the manual
checklist before any public launch. Firebase Console policy/domain/template setup
and any UID migration need separate verification or approval. The deleted root
`Dockerfile` is unused by both Compose configurations; hosting explicitly selects
`Dockerfile.hosting`, so restoring the obsolete file is unnecessary.

The normalized release requires the referral flag to be absent. Restore a fresh
normalized schema or follow the [migration 003 runbook](../database/REFERRAL_MIGRATION_RUNBOOK.md)
for a reviewed legacy copy before enabling hosted workers.
