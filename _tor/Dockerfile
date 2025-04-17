# Use Alpine Linux as the base image
FROM alpine:3.21

# Update the repositories and install necessary packages
RUN apk --no-cache --update --upgrade add \
    privoxy \
    tor \
    py3-requests \
    py3-pysocks \
    lyrebird \
    --repository=https://dl-cdn.alpinelinux.org/alpine/edge/community

# Copy the Python script and make it executable
COPY ./check_tor /usr/local/bin/check_tor
RUN chmod +x /usr/local/bin/check_tor/main.py

# Copy the start script and make it executable
COPY ./start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Use the script as an entry point
CMD ["/usr/local/bin/start.sh"]