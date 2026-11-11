# CareConnect: prepare one Ubuntu VM, deploy only after review

Prepared November 3, 2026 while Azure student benefits are pending. This is a deployment
candidate, not a tested running hosted service. Application tests are recorded in
[REMAINING_FEATURES_TEST_GUIDE.md](../testing/REMAINING_FEATURES_TEST_GUIDE.md).

### User build follow-up

The user's Docker build reached dependency installation and failed because the
original hosting manifest pinned Gunicorn 26.2.2, which the package index did not
provide. The pin is corrected to 26.2.0, which the build's available-version list
and [PyPI release files](https://pypi.org/project/gunicorn/26.2.0/) both confirm.
That release requires Python >=3.10 and lists Python 3.12 support. The user completed
the Compose-validation step without reporting an error. The user subsequently
reported the corrected image build completed without error. Its isolated
`--network none` import check printed `Container imports OK`, and an isolated
HOSTED_MODE Flask factory check with SQLite in memory returned `Health: 200`.
These establish basic image/import/app-startup checks, not full hosted integration.
The user also reported the local coordinator Reports smoke check completed.

## New files and isolation

- `compose.hosting.yml`: separate project `careconnect-hosted`, separate named volumes.
- `Dockerfile.hosting`: explicit runtime COPY paths, Linux Python, non-root UID 10001,
  Gunicorn. Existing empty Dockerfile/local Compose are untouched.
- `requirements-hosting.txt`: original Python manifest plus Linux Gunicorn.
- `.dockerignore`: excludes environments, backups, teammate copies and private keys.
- `deploy/hosting.env.example`: placeholder-only private configuration template.
- `deploy/Caddyfile`: HTTPS proxy to private web:8000.
- `deploy/check_schema.py`: read-only schema and uniqueness/capacity preflight.
- `.gitignore`: also protects Firebase keys, deployment secrets and database backups.

Flask uses secure session cookies and trusts one proxy only in explicit HOSTED_MODE=1.
The web port has no host binding: only Caddy publishes 80/443. Never expose the app
directly while trusting forwarded headers. MySQL, RabbitMQ and management UI remain
on the Docker network without public ports. Hosted mode blocks legacy demo request
access even if testing/debug would otherwise allow it. Existing local behavior is kept.

## Checks available now, without starting a database

Run in a terminal where Docker Desktop/Compose is available, from the project root:

```cmd
docker compose -f compose.hosting.yml config --no-interpolate --quiet
docker build -f Dockerfile.hosting -t careconnect-hosted:local .
```

The first validates Compose without printing private resolved environment values.
The second builds only an image; it does not start workers, import SQL or change the
current database. Neither was executable in the implementation tool terminal because
Docker CLI was unavailable. Record actual results before calling the package ready.
Do not use `docker compose config` without quiet/no-interpolate with real secrets
when collecting screenshots or sharing logs.

## VM preparation after Azure is activated

Use an available x86-64 Ubuntu VM with adequate memory for MySQL, RabbitMQ and Python
processes (start planning around 4 GB, then measure). Review the portal's actual total
estimate, including disk/public IP/network, against student credit before creating it.
There is no assumption that 12-month credit means 12 months of this VM for free.
Deploy only the reviewed runtime repository files, not the Windows venv or backups.
No git mutation or remote resource creation is authorized by this document alone.

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

Use the existing Firebase project matching the frontend web configuration; changing
FIREBASE_PROJECT_ID alone does not replace the frontend config. Add the eventual
website hostname to Firebase's authorized domains with the project owner. Confirm
the VM's system clock is synchronized, as the local demo previously rejected tokens
when the server clock was behind.

Point SITE_DOMAIN's DNS to the VM, permit HTTPS/HTTP for Caddy and restrict SSH to the
administrators' addresses. Caddy can obtain a public certificate only when that DNS
and inbound traffic work. Its data/config volumes retain certificates across restarts.

## Database and launch gates — separate approval required

Do not run baseline/reset scripts or migration 001 against the local or hosted database.
Choose a reviewed current synthetic export whose schema already includes approved
workflow/Firebase changes. Restore into the NEW hosted volume only after explicit
approval and after verifying target/project/database. No SQL is automatically mounted
under docker-entrypoint-initdb.d and the image contains no schema/seed/backup scripts.

Future approved commands on the VM, from the project root:

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

Review imported requests/deadlines before the final start. The two hosted deadline
processes use --apply and will perform real timeout/overdue processing. Existing
October demo requests may be overdue; do not reset their original SLA to hide that.

Only after schema, secrets, DNS, cost and deadline effects have been reviewed:

```sh
docker compose --env-file deploy/.env.hosting -f compose.hosting.yml up -d
docker compose --env-file deploy/.env.hosting -f compose.hosting.yml ps
docker compose --env-file deploy/.env.hosting -f compose.hosting.yml logs --tail 50 web matching notifications outbox
```

Topology setup completes before consumers; read-only schema check completes before
web/workers/scanners. Running services restart unless stopped; init forwards shutdown
signals. Persistent MySQL/RabbitMQ volumes and outbox provide the existing recovery
behavior; at-least-once notifications can retry. Back up the hosted DB regularly to
private storage separate from its VM disk and review restore before executing it.
Never use `down -v`, delete volumes, or restore over an existing dataset without review.

## Completion checks and limits

After an actual launch: verify HTTPS login for all SQL roles, authorized Firebase
domain, private DB/broker ports, logs for all five consumers and outbox, both deadline
processes and persistent data after an approved restart. Coordinate one synthetic
request through matching/notification with the tester instead of repeating every path.
Do not publish admin UIs or credentials to demonstrate queues; use controlled evidence.

Still unverified: live schema preflight, hosted MySQL/RabbitMQ and worker integration,
Gunicorn serving requests, HTTPS/DNS, container restart behavior and actual cloud/network/Firebase
integration. Existing MySQL8.0/RabbitMQ3.13 tags preserve project compatibility; evaluate
supported/patched versions before broader public use rather than silently upgrading
the database/broker here. This is a single-VM university demo, with no multi-host HA,
DLQ/bounded consumer retries or disaster-recovery guarantee.

Reference behavior: [Flask proxy configuration](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/),
[Compose dependency conditions](https://docs.docker.com/compose/how-tos/startup-order/),
[Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https), and
[Gunicorn package release](https://pypi.org/project/gunicorn/26.2.0/). These support the configuration design;
they do not establish a successful build or deployment of this project.
