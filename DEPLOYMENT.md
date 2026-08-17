# Deploying SupportPilot AI

Two parts: running it reproducibly with Docker (locally, or anywhere
that runs containers), and actually putting it somewhere reachable on
the internet. This covers both, plus one architectural tradeoff worth
understanding *before* you deploy, not after.

## Part 1: Docker (local, reproducible)

```bash
docker compose up --build
```

This builds the image (see `Dockerfile`) and starts the app at
http://localhost:8000 — the same single FastAPI process that serves
both the API and the frontend, exactly like `uv run uvicorn api:app`
does locally, just containerized.

Why one image, not the separate frontend/backend Dockerfiles the
original phase plan assumed: Phase 4 deliberately merged them — the
frontend is served BY the FastAPI app (`GET /`) specifically to avoid
CORS — so there's only one real service here to containerize.

Environment variables (`GEMINI_API_KEY`, `PINECONE_API_KEY`, etc.) come
from your `.env` file via `env_file:` in `docker-compose.yml` — nothing
is hardcoded into the image (`.env` is explicitly excluded via
`.dockerignore`, since a baked-in `.env` could leak secrets if the image
were ever pushed to a registry).

First time only, seed the data (same scripts as local dev, just run
inside the running container):

```bash
docker compose exec supportpilot uv run python seed_crm.py
docker compose exec supportpilot uv run python ingest_kb.py
```

Stop it with `docker compose down`. Your data persists in `./data` on
your host machine (via the bind mount in `docker-compose.yml`), so it's
still there next time you `docker compose up` — editing a file in
`data/kb/` on your host and restarting the container picks up the
change too, no rebuild needed.

## Part 2: Deploying to the cloud

### Why Cloud Run, given you're on GCP's free tier

For a single containerized app like this one, **Google Cloud Run** is
the right fit:
- **The free tier is genuinely ongoing, not a trial**: roughly 2 million
  requests and 180,000 vCPU-seconds per month, every month, as part of
  GCP's "Always Free" tier — not a time-limited credit. For a learning
  project's traffic, this should cost $0.
- **Serverless**: no VM to patch, size, or keep running. It scales to
  zero when nobody's using it (you pay nothing while idle) and spins up
  on demand.
- **Deploys straight from your Dockerfile**: `gcloud run deploy --source .`
  builds and deploys in one command — Cloud Build handles the Docker
  build for you.

The other GCP options are worse fits here: a Compute Engine VM means you
manage the OS/patching/uptime yourself for no benefit at this scale; GKE
(Kubernetes) is built for orchestrating many services, not one small
container.

**One clarification on "free":** if this is a newer GCP account, you
likely also have a separate 90-day, $300 trial credit on top of Cloud
Run's Always Free tier (which doesn't expire). Either way, a low-traffic
deployment of this app should stay within Always Free indefinitely.

### The persistence tradeoff — read this before deploying

This app stores conversations, customers, and tickets in a local SQLite
file (`data/supportpilot.db`). That works great with Docker Compose's
volume mount (Part 1), or on a regular server with a persistent disk. It
does **not** work the same way on Cloud Run:

- Cloud Run's container filesystem is **ephemeral by default** — local
  writes vanish whenever the instance restarts, which happens often with
  scale-to-zero (essentially, after any period of inactivity).
- Cloud Run *does* support mounting a Cloud Storage bucket as a volume
  for persistence — but Google's own documentation is explicit that this
  uses Cloud Storage FUSE, which **provides no file locking**: "When
  multiple writes try to replace a file, the last write wins and all
  previous writes are lost." For a SQLite file specifically, under any
  concurrent access, that's a real corruption risk, not just a minor
  inconvenience.

**My recommendation: deploy to Cloud Run *without* trying to solve
this.** Accept that conversation history and tickets reset periodically
— each cold start effectively gives you a fresh `data/supportpilot.db`,
reseeded from whatever was baked into the image at build time. For a
demo, portfolio piece, or continued learning, that tradeoff is genuinely
fine, and not worth solving yet. If you outgrow it, the real fix is
swapping SQLite for a managed database — Cloud SQL (Postgres/MySQL) is
the natural next step — but that's a real architecture change (new
connection code in `memory.py`/`crm.py`), not a Phase 12 concern. Worth
being its own future phase, not something to bolt on here.

Practically: **run the seed scripts locally before deploying**, so the
seeded customers and embedded KB are baked into the image itself (Cloud
Run uses whatever is in `./data` at `docker build`/deploy time, since
there's no volume mount overriding it in this deployment path). That way
the KB and fake customers survive every restart, even though live
conversations/tickets don't.

### Step-by-step: deploy to Cloud Run

**Prerequisites:**
- A GCP project with billing enabled (required even for Always Free
  usage — GCP just won't charge you within the free tier limits).
- The `gcloud` CLI installed, or use Cloud Shell in the browser (skips a
  local install entirely — open https://console.cloud.google.com and
  click the terminal icon).

**1. Authenticate and set your project:**
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

**2. Seed your data locally first** (see the persistence note above —
this bakes the KB and fake customers into the image):
```bash
uv run python seed_crm.py
uv run python ingest_kb.py
```

**3. Enable the services you'll need:**
```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com
```

**4. Deploy directly from source.** This is the simplest path — Cloud
Build reads your `Dockerfile` and handles the build for you, no local
Docker daemon strictly required for this step:
```bash
gcloud run deploy supportpilot-ai \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=your-key,GEMINI_MODEL=gemini-2.5-flash,PINECONE_API_KEY=your-key,PINECONE_INDEX_NAME=supportpilot-kb
```
- `--allow-unauthenticated` makes it publicly reachable with no login —
  right for a demo. Drop it if you want to restrict access.
- `--set-env-vars` is the quick way to pass your API keys. It works, but
  the values are visible in the Cloud Run console/config afterward. For
  anything beyond a personal demo, look into `--set-secrets` with Google
  Secret Manager instead — worth doing before sharing the URL publicly,
  not required just to get this running today.

**5. Cap your costs** (cheap insurance, costs nothing to set):
```bash
gcloud run services update supportpilot-ai \
  --region us-central1 \
  --max-instances 3 \
  --min-instances 0
```
`--min-instances 0` is what keeps this within Always Free — it scales to
zero and only bills for actual request time. `--max-instances 3` is a
safety cap so a traffic spike or a bug can't run up a bill.

**6. Get your URL:**
```bash
gcloud run services describe supportpilot-ai --region us-central1 --format='value(status.url)'
```
Open it — that's your live SupportPilot AI.

**Redeploying after changes:** re-run the same `gcloud run deploy`
command from step 4. Cloud Run creates a new revision and shifts traffic
to it automatically; the previous revision stays available if you need
to roll back (`gcloud run services update-traffic`).

**Cleaning up**, if you're just testing and want zero chance of any
charge:
```bash
gcloud run services delete supportpilot-ai --region us-central1
```
