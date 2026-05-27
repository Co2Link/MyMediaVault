FROM node:24-bookworm-slim AS deps
WORKDIR /app/apps/worker

COPY .npmrc apps/worker/package.json apps/worker/package-lock.json ./
COPY packages/core /app/packages/core
RUN npm ci --install-links=false --ignore-scripts
RUN npm --prefix ../../packages/core ci

FROM node:24-bookworm-slim AS builder
WORKDIR /app/apps/worker

COPY --from=deps /app/apps/worker/node_modules ./node_modules
COPY apps/worker .
COPY packages/core /app/packages/core
COPY --from=deps /app/packages/core/node_modules /app/packages/core/node_modules

RUN npm --prefix ../../packages/core run build
RUN npm run build

FROM node:24-bookworm-slim AS runner-deps
WORKDIR /app/apps/worker

COPY .npmrc apps/worker/package.json apps/worker/package-lock.json ./
COPY packages/core/package.json packages/core/package-lock.json /app/packages/core/
COPY --from=builder /app/packages/core/dist /app/packages/core/dist
RUN npm ci --install-links=false --ignore-scripts --omit=dev
RUN npm --prefix ../../packages/core ci --ignore-scripts --omit=dev

FROM node:24-bookworm-slim AS runner
WORKDIR /app/apps/worker

ENV NODE_ENV=production

COPY --from=builder /app/apps/worker/package.json ./package.json
COPY --from=runner-deps /app/apps/worker/node_modules ./node_modules
COPY --from=builder /app/apps/worker/dist ./dist
COPY --from=builder /app/packages/core/package.json /app/packages/core/package.json
COPY --from=builder /app/packages/core/dist /app/packages/core/dist
COPY --from=runner-deps /app/packages/core/node_modules /app/packages/core/node_modules

RUN node -e "import('@mymediavault/core/db')"

CMD ["node", "dist/event-worker.js"]
