FROM node:24-alpine AS frontend-build

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY scripts ./scripts
COPY tests ./tests
COPY public ./public
RUN npm run vendor && npm test

FROM nginxinc/nginx-unprivileged:1.31.6-alpine3.24

COPY --from=frontend-build /build/public/ /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/conf.d/default.conf

USER 101
EXPOSE 8080
