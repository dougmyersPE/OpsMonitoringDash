# Stage 1: Build React SPA
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# VITE_API_BASE_URL uses relative /api/v1 — Nginx proxies to backend, no absolute URL needed
RUN npm run build

# Stage 2: Serve static files via nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
