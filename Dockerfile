# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────
# Stage 1: Build the React/Vite app
# ─────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency manifests first for layer caching
COPY package.json ./
RUN npm install

# Copy the rest of the source
COPY . .

# Build args for the API URL (injected at build time)
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ─────────────────────────────────────────────────────────────
# Stage 2: Serve with nginx
# ─────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS production

# Remove default nginx static content
RUN rm -rf /usr/share/nginx/html/*
RUN apk add --no-cache wget python3 py3-pip

# Copy built app
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy our nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Local admin backend (same container, proxied by nginx at /api/*)
COPY backend /app/backend
COPY backend/admin_requirements.txt /app/backend/admin_requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /app/backend/admin_requirements.txt

# Entrypoint starts local admin API first, then nginx in foreground
COPY docker/start.sh /start.sh
RUN chmod +x /start.sh

# Expose port 80 (HTTPS is handled by Cloud LB or certbot outside container)
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q --spider http://localhost/health || exit 1

CMD ["/start.sh"]
