FROM node:24-bookworm-slim AS deps
WORKDIR /app/apps/functions

COPY apps/functions/package.json apps/functions/package-lock.json apps/functions/.npmrc ./
COPY packages/core /app/packages/core
RUN npm --prefix ../../packages/core ci
RUN npm ci

FROM node:24-bookworm-slim AS builder
WORKDIR /app/apps/functions

COPY --from=deps /app/apps/functions/node_modules ./node_modules
COPY apps/functions .
COPY packages/core /app/packages/core
COPY --from=deps /app/packages/core/node_modules /app/packages/core/node_modules

RUN npm --prefix ../../packages/core run build
RUN npm run build

FROM node:24-bookworm-slim AS runner
WORKDIR /app/apps/functions

ENV NODE_ENV=production

COPY --from=builder /app/apps/functions/package.json ./package.json
COPY --from=builder /app/apps/functions/package-lock.json ./package-lock.json
COPY --from=builder /app/apps/functions/node_modules ./node_modules
COPY --from=builder /app/apps/functions/dist ./dist
COPY --from=builder /app/packages/core /app/packages/core

CMD ["npm", "run", "scheduled-worker"]
