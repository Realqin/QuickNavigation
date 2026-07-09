FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.redpanda.conf /etc/nginx/conf.d/default.redpanda.conf
COPY nginx.kafka-ui.conf /etc/nginx/conf.d/default.kafka-ui.conf
COPY docker-entrypoint.sh /docker-entrypoint.custom.sh
RUN sed -i 's/\r$//' /docker-entrypoint.custom.sh && chmod +x /docker-entrypoint.custom.sh
COPY --from=builder /app/dist /usr/share/nginx/html
ENV KAFKA_CONSOLE_PROVIDER=redpanda
EXPOSE 80
ENTRYPOINT ["/docker-entrypoint.custom.sh"]
CMD ["nginx", "-g", "daemon off;"]
