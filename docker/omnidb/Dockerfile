# ARM64 原生构建 OmniDB（离线友好：使用 vendor 源码包）
FROM python:3.10-slim-bookworm

ARG OMNIDB_VERSION=3.0.3b

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        gcc \
        g++ \
        libldap2-dev \
        libsasl2-dev \
        libssl-dev \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash omnidb

USER omnidb
WORKDIR /home/omnidb

COPY vendor/ /tmp/vendor/
RUN set -eux; \
    if [ -f "/tmp/vendor/OmniDB-${OMNIDB_VERSION}.tar.gz" ]; then \
      cp "/tmp/vendor/OmniDB-${OMNIDB_VERSION}.tar.gz" /tmp/omnidb-src.tar.gz; \
    else \
      apt-get update \
      && apt-get install -y --no-install-recommends wget \
      && wget -q "https://github.com/OmniDB/OmniDB/archive/${OMNIDB_VERSION}.tar.gz" -O /tmp/omnidb-src.tar.gz \
      && rm -rf /var/lib/apt/lists/*; \
    fi; \
    tar -xzf /tmp/omnidb-src.tar.gz \
    && mv "OmniDB-${OMNIDB_VERSION}" OmniDB \
    && rm /tmp/omnidb-src.tar.gz

WORKDIR /home/omnidb/OmniDB
COPY requirements-arm64.txt /tmp/requirements-arm64.txt
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip config set global.timeout 120 \
    && pip install --no-cache-dir setuptools wheel \
    && pip install --no-cache-dir -r /tmp/requirements-arm64.txt

USER root
COPY patch_omnidb.py /tmp/patch_omnidb.py
RUN python3 /tmp/patch_omnidb.py && rm -f /tmp/patch_omnidb.py

USER root
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
