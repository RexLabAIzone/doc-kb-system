# Doc-KB System

Document Knowledge Base — AI-powered document management system with full-text search, classification, knowledge graph, semantic recommendations, and health check.

## 系统架构

```
┌──────────────┐    ┌───────────┐    ┌──────────────┐
│   前端       │───▶│  后端      │───▶│   PostgreSQL  │
│   (Vue 3)    │    │ (FastAPI) │    │  (pgvector)   │
└──────────────┘    │           │    ├──────────────┤
                    │           │───▶│ Elasticsearch │
┌──────────────┐    │           │    ├──────────────┤
│  文档解析器   │───▶│           │───▶│    Ollama     │
│  (独立服务)   │    └───────────┘    │ (qwen2.5:7b)  │
└──────────────┘                      │  + bge-m3     │
                                      └──────────────┘
```

## 服务列表

| 服务 | 说明 | 默认资源 |
|------|------|----------|
| `postgres` | pgvector 数据库（文档、向量嵌入、元数据） | 2GB 内存, 2 CPU |
| `elasticsearch` | 全文搜索引擎（IK 中文分词） | 2GB 内存, 2 CPU |
| `ollama` | 大语言模型 qwen2.5:7b + 嵌入模型 bge-m3 | 12GB 内存, 6 CPU |
| `doc-parser` | 后台文档扫描与文本提取 | 1GB 内存, 2 CPU |
| `backend` | FastAPI API 服务 + 流水线调度 | 1GB 内存, 1 CPU |
| `frontend` | Vue 3 单页应用（Nginx 托管） | 256MB 内存, 0.5 CPU |

## 环境要求

- **Linux** 服务器（x86_64，推荐 Ubuntu/Debian）
- **16GB+ 内存**（最低要求，推荐 32GB — Ollama qwen2.5:7b 占用约 8GB）
- **50GB+ 空闲磁盘**（用于数据库、ES 索引、缓存解析结果）
- Docker 与 Docker Compose（安装脚本会自动安装）
- SMB 或 NFS 挂载的文档源（可选，通常需要）

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/RexLabAIzone/doc-kb-system.git
cd doc-kb-system

# 2. 配置环境变量
cp .env.example .env
vi .env                          # 设置 PG_PASSWORD 和 JWT_SECRET

# 3. 运行安装脚本（需 root 权限）
sudo bash install.sh

# 4. 挂载文档源
mount -t cifs //nas-server/share /data/originals -o username=user,password=pass
# 或使用 NFS 挂载

# 5. 访问前端界面 http://<服务器IP>
```

## 配置说明

### 环境变量（`.env`）

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `PG_PASSWORD` | **是** | — | PostgreSQL 密码 |
| `JWT_SECRET` | **是** | — | JWT 签名密钥（最少 32 字符） |

### Docker Compose 自定义

通过创建 `docker-compose.override.yml` 自定义资源限制或端口映射：

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '4'
```

### 添加文档源

可通过管理界面或 API 添加文档源：

```bash
curl -X POST http://localhost:8000/api/sources \
  -H "Content-Type: application/json" \
  -d '{"name": "我的书库", "path": "/data/originals", "source_type": "smb"}'
```

## 数据处理流程

1. **扫描** — `_continuous_scan_loop` 每 5 分钟运行，将新增文件添加到数据库
2. **解析** — 流水线从 `.txt/.epub/.mobi/.azw3/.doc` 文件提取文本（PDF 默认跳过）
3. **增强** — Ollama qwen2.5:7b 对每篇文档进行分类（标题、作者、体裁、摘要、标签）
4. **嵌入** — bge-m3 生成向量嵌入用于语义搜索
5. **索引** — 文档写入 Elasticsearch 实现全文搜索

## 健康检查模块

独立健康检查器可扫描目录并验证文件完整性：

```bash
# 通过 API
curl http://localhost:8000/api/health-check/sources
curl -X POST "http://localhost:8000/api/health-check/start?scan_root=/data/originals"

# 浏览子目录
curl "http://localhost:8000/api/health-check/browse?path=/data/originals"
```

## 运维管理

### 备份（每日自动）

手动执行：
```bash
./backup.sh
```

备份文件存储在 `/mnt/nas/FileZol/backups/postgres/`（可自定义路径）。

### 恢复

```bash
docker exec -i postgres pg_restore -U docadmin -d docdb \
  --format=custom --clean < /path/to/backup.dump
```

### 清理 Docker 资源

```bash
docker system prune -f
docker image prune -a -f
```

## 流水线状态

```bash
curl http://localhost:8000/api/documents/pipeline-status
# {"running":true,"phase":"enrich","current":42,"total":6150,"errors":5}
```

## 许可证

MIT
