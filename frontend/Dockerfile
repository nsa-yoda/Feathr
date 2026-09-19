FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY public/ /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/conf.d/default.conf

USER 101
EXPOSE 8080
