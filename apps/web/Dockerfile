FROM node:24-bookworm-slim AS deps
WORKDIR /app

COPY package.json package-lock.json .npmrc ./
RUN npm ci

FROM node:24-bookworm-slim AS builder
WORKDIR /app

ENV DATABASE_URL="sqlserver://localhost:1433;database=placeholder;user=sa;password=Password123!;encrypt=true;trustServerCertificate=true"
ENV AUTH_SECRET="build-time-secret"
ENV AUTH_MICROSOFT_ENTRA_ID_ID="build-time-client-id"
ENV AUTH_MICROSOFT_ENTRA_ID_SECRET="build-time-client-secret"
ENV AUTH_MICROSOFT_ENTRA_ID_ISSUER="https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000/v2.0"
ENV MMV_ADMIN_OBJECT_IDS="[]"
ENV MMV_ADMIN_GROUP_OBJECT_IDS="[]"

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npx prisma generate
RUN npm run build

FROM node:24-bookworm-slim AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/package-lock.json ./package-lock.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/src ./src
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/load-env.ts ./load-env.ts
COPY --from=builder /app/tsconfig.json ./tsconfig.json
COPY --from=builder /app/next.config.ts ./next.config.ts
COPY --from=builder /app/postcss.config.mjs ./postcss.config.mjs
COPY --from=builder /app/prisma.config.ts ./prisma.config.ts

EXPOSE 3000

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
