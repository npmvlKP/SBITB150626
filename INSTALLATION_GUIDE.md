# SBITB-150626 Installation Guide

## Dependency Groups

This project uses optional dependency groups in `pyproject.toml` to optimize installation time and avoid unnecessary dependencies during early phases.

### Core Installation (Phase 0-7)
```bash
pip install SBITB150626
```
Installs core trading system without heavy ML dependencies (~2GB).

### With ML Dependencies (Phase 8-9: Sentiment + RAG)
**IMPORTANT:** torch + transformers are ~8GB. Install them separately.

```bash
# Step 1: Install PyTorch CPU-only (avoids CUDA bloat)
pip install torch==2.5.1+cpu torchvision==0.20.1+cpu -f https://download.pytorch.org/whl/torch_stable.html

# Step 2: Install ML optional dependencies
pip install "SBITB150626[ml]"
```

### With Feast Feature Store (Phase 9+)
```bash
pip install "SBITB150626[feast]"
```
**NOTE:** Feast requires a running feature server and extensive configuration. Only install when needed.

### All Optional Dependencies
```bash
pip install "SBITB150626[ml,feast]"
```

## Docker Environment Setup

### 1. Create your secrets file
```bash
cd deployment
cp .env.docker.example .env.docker
```

### 2. Generate secure passwords
```bash
# Linux/macOS/WSL2
export TIMESCALEDB_PASSWORD=$(openssl rand -base64 32)
export GRAFANA_PASSWORD=$(openssl rand -base64 32)
export REDIS_PASSWORD=$(openssl rand -base64 32)
export GRAFANA_SECRET_KEY=$(openssl rand -base64 32)

# Windows (PowerShell)
$env:TIMESCALEDB_PASSWORD = -join ((33..126) | Get-Random -Count 32 | % {[char]$_})
```

### 3. Update .env.docker with generated values
Edit `deployment/.env.docker` and replace the placeholder values with your generated secrets.

### 4. Start infrastructure
```bash
docker-compose up -d
```

## Phase Compatibility

| Phase | Dependencies | Install Command |
|-------|-------------|-----------------|
| 0-7   | Core only   | `pip install SBITB150626` |
| 8     | + ML        | `pip install "SBITB150626[ml]"` |
| 9     | + Feast     | `pip install "SBITB150626[ml,feast]"` |

## Quick Start

```bash
# Clone and install
git clone https://github.com/npmvlKP/SBITB150626.git
cd SBITB150626

# Core install (fast)
pip install -e .

# Or with dev tools
pip install -e ".[dev]"

# Full ML stack (when ready for Phase 8+)
pip install torch==2.5.1+cpu torchvision==0.20.1+cpu -f https://download.pytorch.org/whl/torch_stable.html
pip install -e ".[ml]"
