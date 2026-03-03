web: sh -c "
  python manage.py migrate &&
  (python manage.py start_payment_listener &) &&
  OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.default.svc.cluster.local:4318 \
  OTEL_SERVICE_NAME=veribroke \
  gunicorn -c gunicorn.conf.py --workers 1 --bind 0.0.0.0:8111 veribroke.wsgi:application --access-logfile - --error-logfile -
"
