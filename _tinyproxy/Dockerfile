FROM alpine:3.24

RUN apk add --no-cache tinyproxy \
    && mkdir -p /var/log/tinyproxy /var/run/tinyproxy \
    && chown -R tinyproxy:tinyproxy \
        /var/log/tinyproxy \
        /var/run/tinyproxy \
        /etc/tinyproxy

USER tinyproxy

CMD ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]