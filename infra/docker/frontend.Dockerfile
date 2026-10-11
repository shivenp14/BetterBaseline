# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS build
WORKDIR /srv/frontend
ENV NEXT_TELEMETRY_DISABLED=1
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci --no-audit --no-fund
COPY frontend/app ./app
COPY frontend/lib ./lib
COPY frontend/components ./components
COPY frontend/next.config.ts frontend/tsconfig.json frontend/next-env.d.ts ./
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN npm run build

FROM node:24-bookworm-slim AS runtime
WORKDIR /srv/frontend
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build --chown=node:node /srv/frontend/package.json ./
COPY --from=build --chown=node:node /srv/frontend/node_modules ./node_modules
COPY --from=build --chown=node:node /srv/frontend/.next ./.next
COPY --from=build --chown=node:node /srv/frontend/next.config.ts ./
USER node
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
 CMD node -e "fetch('http://127.0.0.1:3000').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
CMD ["npm", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
