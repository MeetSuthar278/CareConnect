# Deployment guide

## Local setup (Windows)

Install Python 3.12 and Docker Desktop. Clone the main branch and open the repository folder.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For a new environment, prepare `.env` using `.env.example` and approved private credentials. Keep the Firebase Admin JSON outside the repository. Start MySQL and RabbitMQ only if compatible containers are not already running.

```powershell
docker compose up -d mysql rabbitmq
```

Local host connections use MySQL port 3307 and RabbitMQ port 5673. Prepare a reviewed database export or compatible schema before starting. Never reset an existing database.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\check_health.ps1
```

Open http://127.0.0.1:5000. The supervisor starts nine processes. If startup detects pending work, review it before authorizing `-ProcessPending`.

To stop only the managed application processes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_local.ps1
```

## Azure hosting

The application uses `compose.hosting.yml`, `Dockerfile.hosting` and a private `deploy/.env.hosting`. The database must be imported separately. The schema check must pass before starting the web application and workers.

Use the [hosting runbook](hosting/HOSTING_RUNBOOK.md) for the full procedure, backups, secrets, permissions and recovery. Do not run destructive SQL or recreate live volumes as a routine update.

Live URL: https://careconnect-group4.westus2.cloudapp.azure.com
