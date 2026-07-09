FROM provectuslabs/kafka-ui:v0.7.2

USER root
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

ENV DYNAMIC_CONFIG_ENABLED=false
ENV SPRING_CONFIG_ADDITIONAL-LOCATION=file:/config/application.yml

ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
