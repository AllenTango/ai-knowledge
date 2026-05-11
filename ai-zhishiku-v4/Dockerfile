FROM python:3.10-slim

LABEL maintainer="ai-zhishiku"
LABEL description="AI 知识库助手 —— 自动化知识采集与分发系统"

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV LANG=C.UTF-8
ENV TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        tzdata \
        curl \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.30/supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=9f27ad28c5c57cd133325c2c1896a3e26d80c58c

RUN curl -fsSL "$SUPERCRONIC_URL" -o /usr/local/bin/supercronic \
    && echo "$SUPERCRONIC_SHA1SUM  /usr/local/bin/supercronic" | sha1sum -c - \
    && chmod +x /usr/local/bin/supercronic

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/logs /app/knowledge/raw /app/knowledge/analyzer_output /app/knowledge/articles /app/knowledge/human_review

RUN chmod +x /app/docker/docker-entrypoint.sh

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD pgrep -x supercronic > /dev/null || exit 1

ENTRYPOINT ["/app/docker/docker-entrypoint.sh"]
