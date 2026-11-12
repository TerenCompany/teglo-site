#!/usr/bin/env bash
# Teglo — разовая установка лендинга, демо и бота на сервер.
# Запуск (под root):  bash <(curl -fsSL https://raw.githubusercontent.com/TerenCompany/teglo-site/main/deploy/setup.sh)
# Повторный запуск безопасен: обновит код и настройки (например, когда появится домен).
set -euo pipefail

REPO="https://github.com/TerenCompany/teglo-site.git"
DIR="/opt/teglo"
say() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m!!  %s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "Запустите под root (sudo -i)"; exit 1; }
TTY=/dev/tty  # вопросы читаем с терминала — работает и при curl | bash

say "1/6 Проверяю Docker и git"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq docker-compose-plugin; }
command -v git >/dev/null || { apt-get update -qq && apt-get install -y -qq git; }

say "2/6 Код из GitHub → $DIR"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull -q --ff-only; else git clone -q "$REPO" "$DIR"; fi
cd "$DIR"

say "3/6 Настройки (хранятся только на сервере, в $DIR/.env)"
touch .env; chmod 600 .env
get() { grep -E "^$1=" .env | cut -d= -f2- || true; }
setv() { grep -vE "^$1=" .env > .env.tmp || true; echo "$1=$2" >> .env.tmp; mv .env.tmp .env; chmod 600 .env; }

TOKEN="$(get BOT_TOKEN)"
if [ -z "$TOKEN" ]; then read -rsp "Токен бота @tegloru_bot (ввод скрыт): " TOKEN <"$TTY"; echo; setv BOT_TOKEN "$TOKEN"; fi
OWNER="$(get OWNER_ID)"
if [ -z "$OWNER" ]; then read -rp "Ваш Telegram ID (куда слать заявки): " OWNER <"$TTY"; setv OWNER_ID "$OWNER"; fi
DOMAIN="$(get DOMAIN)"
read -rp "Домен сайта [${DOMAIN:-пока нет — Enter}]: " D_IN <"$TTY"
DOMAIN="${D_IN:-$DOMAIN}"; setv DOMAIN "$DOMAIN"
if [ -n "$DOMAIN" ]; then setv SITE_URL "https://$DOMAIN"; else setv SITE_URL ""; fi

say "4/6 Выбираю, как отдавать сайт"
MODE="none"
PUBLIC_IP="$(curl -fsS4 https://ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
if [ -z "$DOMAIN" ]; then
  MODE="nodomain"
elif ! ss -ltnH '( sport = :443 or sport = :80 )' | grep -q .; then
  MODE="edge"
elif systemctl is-active --quiet caddy 2>/dev/null && [ -f /etc/caddy/Caddyfile ]; then
  MODE="system-caddy"
else
  EDGE="$(docker ps --format '{{.Names}} {{.Image}} {{.Ports}}' | grep -E '(:443->|:80->)' | grep -i caddy | awk '{print $1}' | head -1 || true)"
  if [ -n "$EDGE" ]; then MODE="docker-caddy"; else MODE="other"; fi
fi
echo "$MODE" > deploy/mode
echo "Режим: $MODE"

COMPOSE=(docker compose)
case "$MODE" in
  nodomain) export WEB_BIND="0.0.0.0:8088" ;;
  edge) COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.edge.yml); export DOMAIN ;;
  *) export WEB_BIND="127.0.0.1:8088" ;;
esac
grep -vE '^WEB_BIND=' .env > .env.tmp || true; [ -n "${WEB_BIND:-}" ] && echo "WEB_BIND=$WEB_BIND" >> .env.tmp; mv .env.tmp .env; chmod 600 .env

say "5/6 Запускаю контейнеры (сайт + бот)"
"${COMPOSE[@]}" --env-file .env up -d --build --remove-orphans

BLOCK="# teglo-begin
$DOMAIN, www.$DOMAIN {
	reverse_proxy UPSTREAM
}
# teglo-end"

add_block() { # $1 = путь к Caddyfile на хосте, $2 = upstream
  local f="$1" up="$2"
  cp "$f" "$f.bak-teglo-$(date +%s)"
  sed -i '/# teglo-begin/,/# teglo-end/d' "$f"
  printf '\n%s\n' "${BLOCK/UPSTREAM/$up}" >> "$f"
}

case "$MODE" in
  system-caddy)
    add_block /etc/caddy/Caddyfile "127.0.0.1:8088"
    if caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then systemctl reload caddy
    else warn "Caddyfile не прошёл проверку — откатываю"; cp "$(ls -t /etc/caddy/Caddyfile.bak-teglo-* | head -1)" /etc/caddy/Caddyfile; fi ;;
  docker-caddy)
    CF="$(docker inspect "$EDGE" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}')"
    if [ -z "$CF" ]; then
      CDIR="$(docker inspect "$EDGE" --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy"}}{{.Source}}{{end}}{{end}}')"
      [ -n "$CDIR" ] && CF="$CDIR/Caddyfile"
    fi
    NET="$(docker inspect "$EDGE" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' | awk '{print $1}')"
    if [ -n "$CF" ] && [ -f "$CF" ] && [ -n "$NET" ]; then
      docker network connect "$NET" teglo-web 2>/dev/null || true
      add_block "$CF" "teglo-web:80"
      if docker exec "$EDGE" caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
        docker exec "$EDGE" caddy reload --config /etc/caddy/Caddyfile
      else
        warn "Caddyfile соседнего проекта не прошёл проверку — откатываю, ничего не сломано"
        cp "$(ls -t "$CF".bak-teglo-* | head -1)" "$CF"; MODE="other"
      fi
    else
      MODE="other"
    fi ;;
esac

say "6/6 Автообновление из GitHub каждые 5 минут"
cat > /etc/cron.d/teglo <<EOF
*/5 * * * * root $DIR/deploy/update.sh >> /var/log/teglo-update.log 2>&1
EOF
chmod 644 /etc/cron.d/teglo; chmod +x deploy/update.sh

echo
case "$MODE" in
  nodomain) say "Готово. Сайт: http://$PUBLIC_IP:8088  · бот уже работает. Когда купите домен — направьте A-запись на $PUBLIC_IP и запустите эту команду ещё раз." ;;
  other)    warn "Сайт запущен на 127.0.0.1:8088, но порты 80/443 заняты незнакомым прокси. Добавьте в него проксирование $DOMAIN → 127.0.0.1:8088 или пришлите вывод: ss -ltnp | grep -E ':80 |:443 '; docker ps" ;;
  *)        say "Готово. Сайт: https://$DOMAIN (сертификат выпустится за минуту, если A-запись домена указывает на $PUBLIC_IP) · бот работает." ;;
esac
docker ps --filter name=teglo --format 'table {{.Names}}\t{{.Status}}'
