FROM nginx:latest

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY qn-terminal-bootstrap.js /etc/nginx/qn-terminal-bootstrap.js
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8182
ENTRYPOINT ["/docker-entrypoint.sh"]
