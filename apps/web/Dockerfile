FROM node:24-bookworm-slim AS deps
WORKDIR /app/apps/web

COPY .npmrc apps/web/package.json apps/web/package-lock.json ./
COPY packages/core /app/packages/core
RUN npm ci --install-links=false --ignore-scripts
RUN npm --prefix ../../packages/core ci

FROM node:24-bookworm-slim AS builder
WORKDIR /app/apps/web

COPY --from=deps /app/apps/web/node_modules ./node_modules
COPY apps/web .
COPY packages/core /app/packages/core
COPY --from=deps /app/packages/core/node_modules /app/packages/core/node_modules

RUN npm --prefix ../../packages/core run build
RUN npm run build

FROM node:24-bookworm-slim AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static

EXPOSE 3000

WORKDIR /app/apps/web

CMD ["node", "server.js"]
