FROM omnidbteam/omnidb:latest

USER root
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh
USER omnidb

ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
