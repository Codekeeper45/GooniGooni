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

# Copy built app
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy our nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80 (HTTPS is handled by Cloud LB or certbot outside container)
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q --spider http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
