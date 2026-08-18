# Multi-stage build for the Next.js frontend.
#
# Three stages because a Next.js production image should not contain the
# toolchain that built it. The final image carries the compiled server, the
# static assets and nothing else — roughly 150MB instead of ~1.2GB with
# node_modules.

# --- deps: install once, cached on package.json alone -----------------------
FROM node:20-alpine AS deps
WORKDIR /app
# Copying only the manifests means this layer is reused on every source
# change — a code edit rebuilds in seconds instead of reinstalling npm.
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

# --- builder: compile ------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# API_ORIGIN is baked into the rewrite config at build time. Inside compose
# the backend is reachable as `api`, not `localhost` — localhost in a
# container means the container itself.
ARG API_ORIGIN=http://api:8000
ENV API_ORIGIN=${API_ORIGIN}
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# --- runner: just enough to serve ------------------------------------------
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000

# Non-root. Costs one line and removes a whole class of container escape.
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

# `output: "standalone"` in next.config produces exactly the files the server
# needs, with its own minimal node_modules.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
