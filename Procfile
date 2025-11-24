web: sh -c "python manage.py migrate && (python manage.py start_payment_listeners &) && gunicorn --workers 1 --bind 0.0.0.0:8111 veribroke.wsgi:application --access-logfile - --error-logfile -"
