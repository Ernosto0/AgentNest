# syntax=docker/dockerfile:1
# The public landing page as a static site behind Caddy. Build context: this directory
# (Railway service root directory = /landing).

# --- Stage 1: static build ---
FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
COPY public ./public

# Optional build-time settings (see README). Empty: the form runs in preview mode, no WhatsApp link.
ARG VITE_WAITLIST_ENDPOINT=""
ARG VITE_WAITLIST_WHATSAPP=""
ENV VITE_WAITLIST_ENDPOINT=${VITE_WAITLIST_ENDPOINT} \
    VITE_WAITLIST_WHATSAPP=${VITE_WAITLIST_WHATSAPP}

RUN npm run build

# --- Stage 2: Caddy static file server ---
FROM caddy:2.8-alpine

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=builder /app/dist /srv/landing

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD ["wget", "--no-verbose", "--tries=1", "-O", "/dev/null", "http://127.0.0.1:8081/healthz"]
