#!/usr/bin/env bash
# DocRAG 隔离验收栈管理脚本（Compose project: docrag-acceptance）
# 用法: ./manage.sh {up|down|start|stop|restart|status|logs|build|rebuild|eval|ps}
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT/docker-compose.acceptance.yml"
COMPOSE=(docker compose -f "$COMPOSE_FILE")

usage() {
  sed -n '2,8p' "${BASH_SOURCE[0]}"
}

cmd="${1:-}"
case "$cmd" in
  build)
    exec "${COMPOSE[@]}" build
    ;;
  rebuild)
    exec "${COMPOSE[@]}" build --no-cache
    ;;
  up)
    shift || true
    exec "${COMPOSE[@]}" up -d --wait "$@"
    ;;
  start)
    exec "${COMPOSE[@]}" start
    ;;
  stop)
    exec "${COMPOSE[@]}" stop
    ;;
  down)
    # 明确不带 -v：保留 draccept_* 数据卷，绝不触碰原 docrag_docrag_* 卷
    exec "${COMPOSE[@]}" down
    ;;
  restart)
    exec "${COMPOSE[@]}" restart
    ;;
  status|ps)
    exec "${COMPOSE[@]}" ps
    ;;
  logs)
    shift || true
    exec "${COMPOSE[@]}" logs -f --tail=100 "$@"
    ;;
  eval)
    shift || true
    # 容器内跑 public_nist 公开评测（默认 run；可传 prepare/run/verify）；挂载宿主 work/ 持久化缓存与报告
    if [ $# -eq 0 ]; then set -- run; fi
    exec docker compose -f "$COMPOSE_FILE" run --rm -v "$ROOT/work:/work" backend sh -c "cd /app && python -m app.evaluation.public_runner $*"
    ;;
  *)
    usage
    exit 1
    ;;
esac
