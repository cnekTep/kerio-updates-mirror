FROM nginx:1.31.3-alpine

# inotify-tools: watch config directory for changes
# bash: required by start.sh (uses local, process substitution, etc.)
RUN apk add --no-cache inotify-tools bash

COPY start.sh   /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

ENTRYPOINT ["/usr/local/bin/start.sh"]