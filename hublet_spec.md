# Hublet
## Implementation Specification

Lightweight personal mini-app platform for OpenClaw

Implementation-ready specification for a single-user system optimized for minimal code, minimal infrastructure, minimal maintenance and zero recurring software/service cost.

## 1. Overview

**Working project name: Hublet.**

Build one small Dockerized service on the dedicated MacBook that already runs OpenClaw. It provides Coffee, Goals and Recipes plugins plus a simple mobile-friendly launcher. OpenClaw remains the primary conversational interface through Discord. The web UI is for browsing, quick manual edits and seeing records at a glance.

```text
iPhone / Mac browser                 Discord
        |                               |
        | home LAN                      v
        v                           OpenClaw
       Hublet <------------------------|
  one container          MCP Streamable HTTP
        |
        +-- Home launcher
        +-- Coffee  -> coffee.db
        +-- Goals   -> goals.db
        +-- Recipes -> recipes.db
```

## 2. Key philosophy and decisions

| Principle | Decision |
| --- | --- |
| Brutally lightweight | Prefer obvious code over abstractions. Remove features before adding infrastructure. |
| One runtime | One public GitHub repo, one runtime container, one Python process, one MCP endpoint and one web server. |
| Plugins are modules | No separate containers, dynamic marketplace, internal RPC, queue or event bus. |
| No duplicate master data | If another app is authoritative, store only additional structured memory. Apple Notes remains canonical for recipes. |
| Agent-first | Discord/OpenClaw handles natural-language capture and reasoning. |
| Simple web UI | Server-rendered pages for browse/edit. No SPA. |
| Semantic tools | Expose coffee.log_shot rather than generic database.insert. |
| No destructive tools | Archive/complete instead of agent-accessible delete in v1. |
| Local by default | Dashboard only needs home-LAN access. No public hosting/TLS/reverse proxy in v1. |
| Boring persistence | SQLite outside the container, tiny migrations and automatic snapshots. |
| Public by design | Source code, schemas, Docker config and docs may be public. Personal data, tokens, machine-specific settings and live databases must never be committed. |
| Completely free | Hublet must require no paid hosting, domain, database, API, CI/CD service or SaaS. Use only free/open-source components and GitHub features that are free for public repositories. |

## 3. Tech stack

| Layer | Choice |
| --- | --- |
| Language | Python 3.13+ |
| Web | FastAPI + Uvicorn; one worker; server-rendered HTML forms, not REST |
| Agent interface | Official MCP Python SDK v2; Streamable HTTP mounted in FastAPI |
| Database | Built-in sqlite3; one SQLite file per plugin |
| UI | Server-rendered HTML + a vendored local copy of Pico CSS; no CDN |
| Container | Docker + Docker Compose |
| CI/CD | GitHub Actions on GitHub-hosted runners -> public GHCR image -> Mac launchd auto-pull/deploy |
| Tests | pytest; high-value tests only |
| Lint | Ruff |

Do not add an ORM, Alembic, Redis, Celery, Postgres, Tailwind, React, Node/npm, WebSockets, Kubernetes, reverse proxy or separate MCP process unless a real later requirement justifies it.

## 4. Repository structure

```text
hublet/
  app/
    main.py
    config.py
    db.py
    auth.py
    runtime.py
    web.py
    plugins/
      coffee.py
      goals.py
      recipes.py
  static/
    pico.min.css
    app.css
  tests/
  compose.yml
  Dockerfile
  pyproject.toml
  .env.example
  .github/workflows/ci-deploy.yml
```

Start with one file per plugin. Split files only when navigation becomes painful. Avoid repository/service/model layers merely for architectural neatness.

## 5. Plugin runtime

Each plugin is one ordinary Python module. A tiny immutable `Plugin` descriptor holds only its identity and direct references to its migrations, MCP tool registration, HTML router and launcher summary. Explicitly register the three descriptors in one tuple. Do not add discovery, lifecycle hooks, configuration schemas or a dynamic plugin framework.

```text
Plugin(
    name: str,
    icon: str,
    db_filename: str,
    migrations: tuple[str, ...],
    register_mcp: callable,
    web_router: APIRouter,
    launcher_summary: callable,
)
```

MCP tools and HTML form handlers must call the same ordinary Python domain functions. The descriptor is only wiring, not a repository, service or model layer. Adding a future fourth plugin should require one explicit registration entry but no rewrite of core MCP, database or launcher code.

## 6. Home / launcher

The root page is an app launcher, not an analytics dashboard. Show three large touch-friendly cards: Coffee, Goals and Recipes. Each may show one small summary such as '2 open beans', '4 active', or '12 cook logs'.

```text
Personal
--------------------------------
[ Coffee ]   [ Goals ]   [ Recipes ]
 2 open        4 active    12 cooks
```

Routes: /, /coffee, /goals, /recipes. Mutations use ordinary POSTed HTML forms followed by redirects; v1 exposes no JSON REST API. Use semantic HTML + a locally vendored Pico CSS file and a very small custom stylesheet. Optimize for iPhone width. Avoid JavaScript unless a specific interaction is materially worse without it.

Local access may use Bonjour/mDNS with a deployment-specific name kept outside the repository. Public examples use `http://hublet.example.test:8787`; `http://localhost:8787` and `http://127.0.0.1:8787` are valid loopback examples. Do not add local DNS infrastructure just for a prettier URL.

## 7. OpenClaw integration

OpenClaw remains native on macOS and continues to receive Discord messages. Register Hublet as one MCP server. Namespace tools by plugin.

```text
coffee.add_bean
coffee.list_beans
coffee.log_shot
coffee.history
coffee.recommend_next
```

```text
goals.create
goals.list
goals.get
goals.log_progress
goals.update
goals.status
```

```text
recipes.link
recipes.search
recipes.get
recipes.log_cook
recipes.history
```

OpenClaw interprets conversational input, resolves the relevant record, invokes tools and explains results. The runtime returns structured facts and deterministic recommendations; OpenClaw supplies natural-language reasoning/presentation.

## 8. Coffee plugin

Purpose: remember beans, espresso settings and outcomes so OpenClaw can help dial in primarily from personal history.

| Table | Minimum fields |
| --- | --- |
| beans | id, name, roaster, roast_date, origin, process, status, notes, created_at |
| shots | id, bean_id, dose_g, yield_g, time_s, grind_setting, grinder, temperature_c, rating, taste_tags_json, notes, created_at |

Recommendation logic must be conservative and history-first. A fast+sour shot may suggest finer; a previous highly rated shot for the same bean is stronger evidence. Change one variable at a time. Return recommendation + evidence.

Explicitly omit equipment management, Bluetooth scales, inventory purchasing, refractometers and advanced charts in v1.

## 9. Goals plugin

Purpose: store durable goals and timestamped progress so OpenClaw does not reconstruct them from chat history.

| Table | Minimum fields |
| --- | --- |
| goals | id, title, description, status, target_value, unit, target_date, created_at, updated_at |
| entries | id, goal_id, value, note, created_at |

Keep modelling crude. No OKR framework, habit tracker, streak engine, reminders, nested project system or scoring algorithm. A goal is a target plus progress entries. Every progress entry is an absolute measurement, never a delta: if a goal is logged at 5 and later at 7, its latest progress is 7, not 12. The newest entry by timestamp is the current measurement.

## 10. Recipes plugin

Apple Notes is the master store for the actual recipe. Do NOT duplicate ingredients, steps or formatted recipe text. Store a reference to the note plus cooking experiments and conclusions.

| Table | Minimum fields |
| --- | --- |
| recipes | id, name, note_reference, tags_json, created_at, updated_at |
| cook_logs | id, recipe_id, rating, changes, notes, conclusion, created_at |

Example: 'Used sirloin instead of chuck, doubled garlic, 3/5. Sirloin worse; keep the garlic.' Log the experiment. OpenClaw can then propose updating the canonical Apple Note using its existing Notes access. This runtime should not implement Notes integration.

The plugin's value is historical structured memory: what changed, how it scored and what was learned.

## 11. Database conventions

| Rule | Decision |
| --- | --- |
| Isolation | coffee.db, goals.db and recipes.db. |
| Persistence | Host mount under `$HOME/.hublet/data/`. Never store live data in Git or the image. |
| IDs | UUID text. |
| Dates | UTC ISO-8601 timestamps; ISO date for date-only fields. |
| Migrations | Handwritten SQL list per plugin using PRAGMA user_version. |
| Connections | Short-lived sqlite3 connections; foreign_keys ON. |
| Journal | SQLite defaults initially; no WAL without measured need. |
| Backup | sqlite3 Connection.backup(), not raw copy of a live DB. |

## 12. Public repository and security

Hublet is intentionally developed in a **public GitHub repository**. The public repository must contain only code and generic example configuration. It must be safe to clone without exposing any personal information or credentials.

Never commit:

- `.env` or secrets files
- MCP/OpenClaw bearer tokens
- Discord tokens, API keys or credentials
- live `.db`, `.sqlite` or backup files
- Apple Notes content or personal exports
- private IP addresses, usernames or machine-specific paths unless they are harmless examples
- SSH/private keys or GitHub credentials

Required `.gitignore` baseline:

```gitignore
.env
.env.*
!.env.example

*.db
*.sqlite
*.sqlite3
data/
backups/
secrets/
*.pem
*.key
.DS_Store
*.egg-info/
.coverage
.coverage.*
coverage.xml
htmlcov/
```

Runtime threat model: one trusted user on a home LAN plus OpenClaw on the same Mac. Never router-port-forward Hublet. Dashboard and MCP authentication are deliberately independent:

- `HUBLET_DASHBOARD_TOKEN` authenticates the dashboard login form. A successful login uses Starlette `SessionMiddleware`, backed by itsdangerous, to create a signed cookie using the separate `HUBLET_SESSION_SECRET`. Its only semantic payload is `{"authenticated": true}`; the raw dashboard token and other user data are never stored in the cookie. The middleware enforces a server-side signature `max_age` of 90 days. The cookie is HttpOnly, SameSite=Lax and Path=/. It is Secure if and only if `HUBLET_PUBLIC_ORIGIN` uses HTTPS, so plain HTTP remains supported for the home-LAN deployment. Credential rotation is explicit: rotating `HUBLET_SESSION_SECRET` revokes all existing sessions; dashboard token rotation alone does not revoke existing sessions.
- Every state-changing dashboard request, including login, must have an `Origin` exactly matching `HUBLET_PUBLIC_ORIGIN`. If `Origin` is absent, the origin parsed from `Referer` must match exactly. Reject requests when both are absent or either supplied value is malformed or mismatched. Repository examples use only `http://hublet.example.test:8787`, `http://localhost:8787` or `http://127.0.0.1:8787`; the real deployment origin stays outside Git.
- `HUBLET_MCP_TOKEN` protects every `/mcp` transport method through an `Authorization: Bearer` header. `HUBLET_MCP_ALLOWED_HOSTS` is the comma-separated allowlist for MCP Host-header validation and uses the SDK wildcard-port syntax `hublet.example.test:*,localhost:*,127.0.0.1:*` in public examples. A dashboard cookie never grants MCP access, and the MCP bearer never grants dashboard access.

All dashboard writes use authenticated HTML forms. V1 has no REST API. Do not implement accounts, OAuth, roles, JWT refresh or cloud identity.

**Do not attach a self-hosted GitHub Actions runner to this public repository.** Public repositories can receive pull requests from forks, and GitHub warns that self-hosted runners can therefore expose the host machine to dangerous code. All repository CI must run on GitHub-hosted runners.

## 13. Docker

```text
services:
  runtime:
    build: .
    restart: unless-stopped
    ports:
      - "8787:8000"
    volumes:
      - ${HOME}/.hublet/data:/data
    env_file:
      - ${HOME}/.hublet/secrets.env
```

Use one Uvicorn worker. Add /health. Run migrations before accepting requests. The container must recover after Docker/Mac restart. Keep OpenClaw outside Docker.

## 14. GitHub push-to-deploy

Goal: pushing trusted code to `main` should automatically update Hublet on the MacBook with no paid service and no inbound connection to the home network.

Use this flow:

```text
git push main
     |
GitHub-hosted Actions
  ruff -> pytest -> docker build
     |
     v only if green
push public image to GHCR
  ghcr.io/example/hublet:latest
     |
     v
Mac launchd job (e.g. every 5 minutes)
  docker compose pull
  docker compose up -d --remove-orphans
     |
GET /health
```

Why this design:

- Standard GitHub-hosted Actions are free for public repositories.
- Public GitHub Packages / GHCR images are free to publish and pull under GitHub's current public-package policy.
- No self-hosted GitHub runner is exposed to public-repository workflows.
- No webhook endpoint, reverse proxy, tunnel or cloud server is required.
- The Mac initiates outbound pulls only.
- Deployment delay of up to the polling interval is acceptable for this project.

The Mac should run a tiny `launchd` job every 5 minutes. The deploy script should:

1. `docker compose pull`
2. detect whether the image changed; if not, exit
3. `docker compose up -d --remove-orphans`
4. call `/health`
5. if health fails, leave a local log entry; automatic rollback is out of scope for v1

Use immutable commit-SHA image tags as well as `latest` so a manual rollback is possible. Do not add Watchtower unless the simple `launchd` script proves unreliable; one shell script is less infrastructure.

### Zero-cost requirement

Hublet must have **$0 recurring software/service cost**. The implementation must not require:

- paid GitHub runners
- paid container registry/storage
- Vercel, Render, Railway, Fly.io or other hosted deployment
- a purchased domain
- hosted database
- paid monitoring/logging
- paid auth provider
- paid APIs for core functionality

Use the existing MacBook, home network, Docker, SQLite, Bonjour/mDNS, GitHub public-repository Actions, public GHCR and local `launchd`. Hardware, electricity, internet access and any existing OpenClaw/model costs are outside Hublet's software/service budget.

## 15. Backup and recovery

Provide one command that snapshots all three databases from `HUBLET_DATA_DIR` to `HUBLET_BACKUP_DIR` using SQLite's online backup API. The intended host directories are `$HOME/.hublet/data/` and `$HOME/.hublet/backups/`, supplied through deployment configuration rather than committed values. Schedule daily with macOS launchd. Thirty daily snapshots is enough initially; the backup folder should also be covered by the Mac's independent backup.

Restore: stop container -> replace affected .db with chosen snapshot -> start container -> verify /health.

## 16. Explicit non-goals

- Public internet dashboard or remote hosting
- Any recurring paid software/service dependency
- Native iOS app/PWA complexity
- React/Vue/Svelte or frontend build chain
- Multiple users/permissions/sharing
- Generic plugin marketplace or dynamic loading
- Cross-plugin event bus
- Postgres/Redis/queues
- Advanced analytics/charts
- Push notifications/reminders
- Coffee Bluetooth/hardware integration
- Recipe master-data duplication from Apple Notes
- Destructive agent tools
- Projects plugin
## 17. Implementation order

| Phase | Deliverable / acceptance criterion |
| --- | --- |
| 1. Foundation | Container, /health, SQLite helper, migration helper, plugin registry. |
| 2. Coffee vertical slice | Discord -> OpenClaw -> MCP -> coffee.db -> response works for log_shot and history. |
| 3. Goals | Add plugin without changing core architecture beyond registration. |
| 4. Recipes | Link Notes recipes and store cook logs only; prove history/conclusion workflow. |
| 5. Launcher | Pico CSS home page and three plugin pages, usable on iPhone over home Wi-Fi. |
| 6. Operations | Independent MCP bearer and signed-cookie dashboard auth, backup command, public GitHub CI, public GHCR image, launchd auto-pull deployment. |
| 7. Stop | Do not add more platform machinery until a real use case demands it. |

## 18. Definition of done

- One public GitHub repository containing no personal data or secrets.
- One Docker container and one Python process.
- Three independent SQLite files persisted outside the container.
- One MCP endpoint registered with OpenClaw.
- Coffee, Goals and Recipes usable naturally from Discord.
- Home launcher reachable from iPhone on the LAN and styled with Pico CSS.
- Apple Notes remains canonical for recipe content.
- Push to main automatically tests, builds a public GHCR image, and is pulled/deployed by the MacBook.
- Daily database snapshots exist and restore procedure is documented.
- System remains understandable without an operations manual or paid cloud services.
- Hublet incurs $0 recurring software/service cost.
## 19. Final architectural constraint

When choosing between a cleaner architecture and fewer moving parts, choose fewer moving parts. Hublet is a personal structured-memory daemon for OpenClaw, not a software platform intended for external customers. The successful v1 is the smallest system that reliably remembers structured personal data, exposes it to the agent and provides a pleasant local browse interface.
