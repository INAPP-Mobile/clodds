# Clodds — AI-powered trading terminal for prediction markets, crypto & futures
# https://github.com/alsk1992/CloddsBot
# Source build (no upstream Docker image published). Based on upstream Dockerfile
# with Railway adaptations: listen on $PORT, root user for volume, healthcheck.
FROM node:22-bookworm-slim AS builder

WORKDIR /app

COPY package.json package-lock.json tsconfig.json ./
COPY src ./src
# postinstall hooks (fix-native-bindings.js, fix-anchor-bn-export.js) live here
COPY scripts ./scripts

RUN npm ci --legacy-peer-deps
RUN npm run build

FROM node:22-bookworm-slim AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV CLODDS_STATE_DIR=/data
ENV CLODDS_WORKSPACE=/data/workspace
# Railway: gateway binds to the injected port (upstream default 18789)
ENV CLODDS_PORT=18789
ENV CLODDS_HOST=0.0.0.0
ENV PORT=18789

COPY package.json package-lock.json ./
# postinstall hooks (fix-native-bindings.js, fix-anchor-bn-export.js) live here
COPY scripts ./scripts
RUN npm ci --omit=dev --legacy-peer-deps

COPY --from=builder /app/dist ./dist
# WebChat static assets are served from ../../public relative to dist/gateway/
COPY public ./public

RUN mkdir -p /data /data/workspace .transformers-cache

# Pre-download embedding model so it's warm at runtime (no first-request hang)
RUN node -e "const{pipeline,env}=require('@xenova/transformers');env.cacheDir='./.transformers-cache';pipeline('feature-extraction','Xenova/all-MiniLM-L6-v2',{quantized:true}).then(()=>console.log('Model cached')).catch(e=>console.error('Model cache failed:',e))"

# Run as root (required for volume mounts on Railway)
USER root

EXPOSE 18789

# Upstream healthcheck — /health endpoint on the gateway port
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
  CMD node -e "fetch('http://localhost:'+(process.env.CLODDS_PORT||18789)+'/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["node", "dist/index.js"]