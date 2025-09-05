# Use Alpine HAProxy as the base image
FROM haproxy:3.2.4-alpine

# Switch to root user
USER root

# Install necessary packages
RUN apk add --no-cache inotify-tools bash

# Copy the start script and make it executable
COPY ./start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Use the script as an entry point
ENTRYPOINT ["/usr/local/bin/start.sh"]
