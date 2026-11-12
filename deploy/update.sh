#!/usr/bin/env bash
# Подтягивает новую версию из GitHub; пересобирает только если что-то изменилось.
set -euo pipefail
cd /opt/teglo
OLD="$(git rev-parse HEAD)"
git pull -q --ff-only
NEW="$(git rev-parse HEAD)"
[ "$OLD" = "$NEW" ] && exit 0
echo "$(date -Is) update $OLD -> $NEW"
MODE="$(cat deploy/mode 2>/dev/null || echo none)"
if [ "$MODE" = "edge" ]; then
  set -a; . ./.env; set +a
  docker compose -f docker-compose.yml -f docker-compose.edge.yml --env-file .env up -d --build --remove-orphans
else
  docker compose --env-file .env up -d --build --remove-orphans
fi
# если сайт отдаёт соседний Caddy в Docker — после пересоздания контейнера возвращаем его в общую сеть
[ -f deploy/edge_net ] && docker network connect "$(cat deploy/edge_net)" teglo-web 2>/dev/null || true
# статика монтируется томом — сайт обновляется сразу; бот пересобирается при изменении кода
