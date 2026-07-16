# Doc-KB System

Document Knowledge Base — AI-powered document management system with full-text search, classification, knowledge graph, and semantic recommendations.

## Architecture

```
┌──────────────┐    ┌───────────┐    ┌──────────────┐
│   Frontend    │───▶│  Backend   │───▶│   Postgres    │
│   (Vue 3)     │    │ (FastAPI)  │    │  (pgvector)   │
└──────────────┘    │            │    ├──────────────┤
                    │            │───▶│ Elasticsearch │
┌──────────────┐    │            │    ├──────────────┤
│  Doc Parser   │───▶│            │───▶│    Ollama     │
│  (Standalone) │    └───────────┘    │ (qwen2.5:7b)  │
└──────────────┘                      │  + bge-m3     │
                                      └──────────────┘
```

## Services

| Service | Description | Default Resources |
|---------|-------------|-------------------|
| `postgres` | pgvector DB (documents, embeddings, metadata) | 2GB RAM, 2 CPUs |
| `elasticsearch` | Full-text search engine with IK analyzer | 2GB RAM, 2 CPUs |
| `ollama` | LLM (qwen2.5:7b) + embedding (bge-m3) models | 12GB RAM, 6 CPUs |
| `doc-parser` | Background doc scanning & text extraction | 1GB RAM, 2 CPUs |
| `backend` | FastAPI API server + pipeline orchestrator | 1GB RAM, 1 CPU |
| `frontend` | Vue 3 SPA via nginx | 256MB RAM, 0.5 CPU |

## Requirements

- **Linux** server (x86_64, Ubuntu/Debian recommended)
- **16GB+ RAM** (minimum, 32GB recommended — Ollama qwen2.5:7b uses ~8GB)
- **50GB+ free disk** (for DB, ES indices, cached parses)
- Docker & Docker Compose (installed by script)
- SMB or NFS mount for document source (optional but typical)

## Quick Start

```bash
# 1. Clone
git clone https://github.com/your-org/doc-kb-system.git
cd doc-kb-system

# 2. Configure
cp .env.example .env
vi .env                          # Set PG_PASSWORD and JWT_SECRET

# 3. Run installer (as root)
sudo bash install.sh

# 4. Mount your document source
mount -t cifs //nas-server/share /data/originals -o username=user,password=pass
# OR symlink an NFS mount

# 5. Access the UI at http://<your-server-ip>
```

## Configuration

### Environment Variables (`.env`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PG_PASSWORD` | **Yes** | — | PostgreSQL password |
| `JWT_SECRET` | **Yes** | — | JWT signing secret (min 32 chars) |

### Docker Compose Override

Customize resource limits or port mappings by creating `docker-compose.override.yml`:

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '4'
```

### Adding Document Sources

Sources are managed through the UI or directly via the API:

```bash
curl -X POST http://localhost:8000/api/sources \
  -H "Content-Type: application/json" \
  -d '{"name": "My Books", "path": "/data/originals", "source_type": "smb"}'
```

## Data Flow

1. **Scan** — `_continuous_scan_loop` runs every 5 min, adds new files from sources to DB
2. **Parse** — Pipeline extracts text from `.txt/.epub/.mobi/.azw3/.doc` files (PDF skipped)
3. **Enrich** — Ollama qwen2.5:7b classifies each doc (title, author, genre, summary, tags)
4. **Embed** — bge-m3 generates vector embeddings for semantic search
5. **Index** — Document indexed into Elasticsearch for full-text search

## Health Check Module

The standalone health checker scans a directory and validates file integrity:

```bash
# Via API
curl http://localhost:8000/api/health-check/sources
curl -X POST "http://localhost:8000/api/health-check/start?scan_root=/data/originals"

# Browse subdirectories
curl "http://localhost:8000/api/health-check/browse?path=/data/originals"
```

## Maintenance

### Backup (automatic daily)

Run manually:
```bash
./backup.sh
```

Backups are stored at `/mnt/nas/FileZol/backups/postgres/` (or configure your own).

### Restore

```bash
docker exec -i postgres pg_restore -U docadmin -d docdb \
  --format=custom --clean < /path/to/backup.dump
```

### Clean stale Docker resources

```bash
docker system prune -f
docker image prune -a -f
```

## Pipeline Status

```bash
curl http://localhost:8000/api/documents/pipeline-status
# {"running":true,"phase":"enrich","current":42,"total":6150,"errors":5}
```

## License

MIT
