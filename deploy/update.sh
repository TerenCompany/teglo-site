#!/usr/bin/env bash
# Подтягивает новую версию из GitHub; пересобирает только если что-то изменилось.
set -euo pipefail
cd /opt/teglo
OLD="$(git rev-parse HEAD)"
git pull -q --ff-only
NEW="$(git rev-parse HEAD)"
[ "$OLD" = "$NEW" ] && exit 0
echo "$(date -Is) update $OLD -> $NEW"
CHANGED="$(git diff --name-only "$OLD" "$NEW")"

MODE="$(cat deploy/mode 2>/dev/null || echo none)"
COMPOSE=(docker compose --env-file .env)
CF=deploy/Caddyfile
if [ "$MODE" = "edge" ]; then
  COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.edge.yml --env-file .env)
  CF=deploy/Caddyfile.edge
fi

# Новый Caddyfile сначала проверяем; если он с ошибкой — откатываемся на прошлую версию.
if echo "$CHANGED" | grep -q '^deploy/Caddyfile'; then
  set -a; . ./.env; set +a
  if ! docker run --rm -e DOMAIN="${DOMAIN:-example.com}" -v "$PWD/$CF:/etc/caddy/Caddyfile:ro" caddy:2-alpine \
       caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
    echo "Caddyfile с ошибкой — откатываю на $OLD"
    git reset -q --hard "$OLD"
    exit 1
  fi
fi

"${COMPOSE[@]}" up -d --build --remove-orphans
# git заменяет файл целиком, а Docker держит старую копию смонтированного файла — пересоздаём web
if echo "$CHANGED" | grep -qE '^(deploy/Caddyfile|docker-compose)'; then
  "${COMPOSE[@]}" up -d --force-recreate web
fi
# если сайт отдаёт соседний Caddy в Docker — возвращаем контейнер в его сеть после пересоздания
[ -f deploy/edge_net ] && docker network connect "$(cat deploy/edge_net)" teglo-web 2>/dev/null || true
# статика (web/) монтируется папкой — новые файлы видны сразу
