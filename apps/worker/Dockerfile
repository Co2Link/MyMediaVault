FROM node:24-bookworm-slim AS deps
WORKDIR /app/apps/worker

COPY .npmrc apps/worker/package.json apps/worker/package-lock.json ./
COPY packages/core /app/packages/core
RUN npm --prefix ../../packages/core ci
RUN npm ci

FROM node:24-bookworm-slim AS builder
WORKDIR /app/apps/worker

COPY --from=deps /app/apps/worker/node_modules ./node_modules
COPY apps/worker .
COPY packages/core /app/packages/core
COPY --from=deps /app/packages/core/node_modules /app/packages/core/node_modules

RUN npm --prefix ../../packages/core run build
RUN npm run build

FROM node:24-bookworm-slim AS runner
WORKDIR /app/apps/worker

ENV NODE_ENV=production

COPY --from=builder /app/apps/worker/package.json ./package.json
COPY --from=builder /app/apps/worker/package-lock.json ./package-lock.json
COPY --from=builder /app/apps/worker/node_modules ./node_modules
COPY --from=builder /app/apps/worker/dist ./dist
COPY --from=builder /app/packages/core /app/packages/core

CMD ["node", "dist/event-worker.js"]
