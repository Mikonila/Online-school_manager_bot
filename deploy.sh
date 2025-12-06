#!/bin/bash
set -e

SERVER="root@77.73.232.142"
TARGET="/root/codimonline"
IMAGE_NAME="mybot"
CONTAINER_NAME="mybot"

echo "🚀 Синхронизирую проект с сервером $SERVER..."
rsync -avz --delete --exclude 'venv' --exclude '__pycache__' ./ $SERVER:$TARGET

echo "🔄 Пересобираю и перезапускаю контейнер..."
ssh $SERVER "
  cd $TARGET && \
  docker build -t $IMAGE_NAME . && \
  docker rm -f $CONTAINER_NAME || true
  docker run -d --name $CONTAINER_NAME --restart unless-stopped $IMAGE_NAME
"

echo "✅ Деплой завершён!"
