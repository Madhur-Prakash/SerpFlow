# SerpFlow frontend.
#
# Vite build, then nginx serving the static bundle and proxying the API so the
# browser talks to a single origin. That matters for the SSE endpoint:
# EventSource has no header API, and a same-origin stream avoids a CORS
# preflight on a long-lived connection.

FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY . .

ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build


FROM nginx:1.27-alpine AS runtime

LABEL org.opencontainers.image.title="SerpFlow frontend" \
      org.opencontainers.image.licenses="Apache-2.0"

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=4s --start-period=5s --retries=4 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
