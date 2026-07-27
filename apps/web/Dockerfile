# Multi-stage build.
#   dev     — Next.js dev server with hot reload, used by docker-compose.override.yml
#   builder — produces the production build
#   runner  — minimal production image (default target)

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------
# devDependencies are required here: `next dev` needs the full toolchain, which
# the production runner deliberately omits. Without this stage the compose
# override mounted source over a production server that does not watch files,
# so "hot reload" never actually happened.
FROM node:20-alpine AS dev
WORKDIR /app
ENV NODE_ENV=development
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 3000
# Bind to 0.0.0.0, otherwise the port is not reachable from outside the container.
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0"]

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
# Production
# ---------------------------------------------------------------------------
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY package*.json ./
RUN npm ci --omit=dev

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/next.config.js ./

EXPOSE 3000

# wget ships with the alpine base image.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD wget -qO- http://localhost:3000/ >/dev/null 2>&1 || exit 1

CMD ["npm", "start"]
