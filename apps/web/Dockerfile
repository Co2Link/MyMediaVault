FROM node:24-bookworm-slim AS deps
WORKDIR /app/apps/web

COPY apps/web/package.json apps/web/package-lock.json apps/web/.npmrc ./
COPY packages/core/package.json /app/packages/core/package.json
RUN npm ci

FROM node:24-bookworm-slim AS builder
WORKDIR /app/apps/web

ENV MONGODB_URI="mongodb://127.0.0.1:27017/mymediavault"
ENV MMV_MONGODB_DB_NAME="mymediavault"
ENV AUTH_SECRET="build-time-secret"
ENV AUTH_MICROSOFT_ENTRA_ID_ID="build-time-client-id"
ENV AUTH_MICROSOFT_ENTRA_ID_SECRET="build-time-client-secret"
ENV AUTH_MICROSOFT_ENTRA_ID_ISSUER="https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000/v2.0"
ENV MMV_ADMIN_OBJECT_IDS="[]"
ENV MMV_ADMIN_GROUP_OBJECT_IDS="[]"

COPY --from=deps /app/apps/web/node_modules ./node_modules
COPY apps/web .
COPY packages/core /app/packages/core

RUN npm --prefix ../../packages/core run build
RUN npm run build

FROM node:24-bookworm-slim AS runner
WORKDIR /app/apps/web

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

COPY --from=builder /app/apps/web/package.json ./package.json
COPY --from=builder /app/apps/web/package-lock.json ./package-lock.json
COPY --from=builder /app/apps/web/node_modules ./node_modules
COPY --from=builder /app/apps/web/.next ./.next
COPY --from=builder /app/apps/web/src ./src
COPY --from=builder /app/apps/web/load-env.ts ./load-env.ts
COPY --from=builder /app/apps/web/tsconfig.json ./tsconfig.json
COPY --from=builder /app/apps/web/next.config.ts ./next.config.ts
COPY --from=builder /app/apps/web/postcss.config.mjs ./postcss.config.mjs
COPY --from=builder /app/packages/core /app/packages/core

EXPOSE 3000

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
