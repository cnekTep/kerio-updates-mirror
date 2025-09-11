import multiprocessing
import os

# Bind only to internal port - Nginx handles external ports
bind = "0.0.0.0:8000"

# Worker calculation
# For CPU-bound: workers = cpu_count + 1
# For I/O-bound: workers = (cpu_count * 2) + 1
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))

# Worker class
worker_class = "sync"  # or "gevent" for async workloads
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50

# Memory management
preload_app = True  # Share code between workers

# Timeouts
timeout = 30
keepalive = 2
graceful_timeout = 30

# Logging
accesslog = "-"  # stdout
errorlog = "-"  # stderr
loglevel = os.getenv("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "mirror"

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Server mechanics
daemon = False
pidfile = "/tmp/gunicorn.pid"
tmp_upload_dir = None


def post_worker_init(worker):
    """Called after worker process fork."""
    # import inside to avoid running in master
    from config.config_env import config
    from utils.watcher import start_env_watcher

    # running watcher on the change .env file
    start_env_watcher(config=config, env_path=config.env_path, worker_pid=worker.pid)


def post_fork(server, worker):
    """Called after worker process fork."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)


def when_ready(server):
    """Called when the server is started."""
    server.log.info(f"Server ready with {workers} workers on internal port 8000")


def worker_int(worker):
    """Called when worker receives SIGINT or SIGQUIT signal."""
    worker.log.info("Worker received INT or QUIT signal")


def on_exit(server):
    """Called when gunicorn is about to exit."""
    server.log.info("Server is shutting down")
