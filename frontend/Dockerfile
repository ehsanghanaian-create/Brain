# ============================================
# Stage 1: Install dependencies
# ============================================

ARG NODE_VERSION=22-slim

FROM node:${NODE_VERSION} AS pnpm-base

COPY docker-cache/pnpm /opt/pnpm
RUN ln -s /opt/pnpm/bin/pnpm.cjs /usr/local/bin/pnpm

FROM pnpm-base AS dependencies

WORKDIR /app

# Copy package-related files to leverage Docker cache
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY docker-cache/pnpm-store /pnpm/store

# All packages are fetched on the host into docker-cache/pnpm-store. Docker's
# outbound network may be unavailable, so dependency installation is offline.
RUN pnpm install --offline --frozen-lockfile --store-dir /pnpm/store

# ============================================
# Stage 2: Build the Next.js application
# ============================================

FROM pnpm-base AS builder

WORKDIR /app

COPY --from=dependencies /app/node_modules ./node_modules
COPY . .

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Build-time env vars — override these with --build-arg or in compose.yml

ENV BUILD_STANDALONE=true

RUN pnpm build

# ============================================
# Stage 3: Production runner
# ============================================

FROM node:${NODE_VERSION} AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
ENV NEXT_TELEMETRY_DISABLED=1

# Copy public assets
COPY --from=builder --chown=node:node /app/public ./public

# Create .next dir with correct permissions for prerender cache
RUN mkdir .next && chown node:node .next

# Copy standalone output and static files
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

# Run as non-root user
USER node

EXPOSE 3000

CMD ["node", "server.js"]
