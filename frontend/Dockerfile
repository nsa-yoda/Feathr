FROM nginxinc/nginx-unprivileged:1.31.6-alpine3.24

COPY public/ /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/conf.d/default.conf

USER 101
EXPOSE 8080
