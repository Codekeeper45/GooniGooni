#!/bin/bash
# deploy-to-gcp.sh
# Run this on openclaw-server via: gcloud compute ssh openclaw-server --zone=us-east1-b -- 'bash -s' < deploy-to-gcp.sh
#
# OR run locally (replace DOCKERHUB_USER with your DockerHub username):
#   gcloud compute ssh openclaw-server --zone=us-east1-b \
#     --command="DOCKERHUB_USER=YOUR_USERNAME bash -s" < deploy-to-gcp.sh

set -e

DOCKERHUB_USER="${DOCKERHUB_USER:-YOUR_DOCKERHUB_USERNAME}"
IMAGE="${DOCKERHUB_USER}/gooni-gooni:latest"
CONTAINER_NAME="gooni"
ENV_FILE="/opt/gooni/admin.env"
RESULTS_DIR="/opt/gooni/results"

echo "=== Gooni Gooni — Deployment Script ==="
echo "Image: $IMAGE"
echo "VM: openclaw-server (34.73.173.191)"
echo ""

# 1. Install Docker if not present
if ! command -v docker &>/dev/null; then
  echo "[1/4] Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
  echo "Docker installed. Please reconnect SSH and re-run this script if needed."
else
  echo "[1/4] Docker already installed ($(docker --version))"
fi

# 2. Pull latest image
echo "[2/4] Pulling image: $IMAGE"
sudo docker pull "$IMAGE"

# 3. Stop old container if running
if sudo docker ps -q --filter name=$CONTAINER_NAME 2>/dev/null | grep -q .; then
  echo "[3/4] Stopping old container..."
  sudo docker stop $CONTAINER_NAME
  sudo docker rm $CONTAINER_NAME
else
  echo "[3/4] No old container to stop"
fi

# 3.5 Ensure runtime dirs/env exist
echo "[3.5/4] Checking runtime env file..."
sudo mkdir -p "$RESULTS_DIR"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: missing $ENV_FILE"
  echo "Create the env file with API_KEY, ADMIN_LOGIN, ADMIN_PASSWORD_HASH, ACCOUNTS_ENCRYPT_KEY, HF_TOKEN"
  exit 1
fi

# 4. Start new container
echo "[4/4] Starting container..."
sudo docker run -d \
  --name $CONTAINER_NAME \
  --restart unless-stopped \
  -p 80:80 \
  -v "$RESULTS_DIR:/results" \
  --env-file "$ENV_FILE" \
  "$IMAGE"

echo ""
echo "=== Deployment complete! ==="
echo "  Frontend: http://34.73.173.191"
echo ""
echo "Container status:"
sudo docker ps --filter name=$CONTAINER_NAME
