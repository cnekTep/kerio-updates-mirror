FROM python:3.14.6-alpine3.24

RUN apk --no-cache --update add tor lyrebird su-exec

COPY ./check_tor/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY --chmod=755 entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/bin/sh", "/tor/start.sh"]