"""
Gunicorn configuration for SEBC project.
Usage: gunicorn -c gunicorn.conf.py SEBC.wsgi:application
"""

import multiprocessing
import os

# Bind
bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:8000')

# Workers
workers = int(os.environ.get('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'sync'
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = os.environ.get('GUNICORN_ACCESS_LOG', '-')
errorlog = os.environ.get('GUNICORN_ERROR_LOG', '-')
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')

# Process naming
proc_name = 'sebc'

# Reload (dev only — disable in production)
reload = os.environ.get('GUNICORN_RELOAD', 'false').lower() == 'true'

# Security
limit_request_line = 8190
limit_request_fields = 100
