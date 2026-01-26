#!/usr/bin/env bash
set -euo pipefail

python manage.py migrate --noinput

if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" && -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]]; then
  python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
username = '${DJANGO_SUPERUSER_USERNAME}'
email = '${DJANGO_SUPERUSER_EMAIL:-}'
password = '${DJANGO_SUPERUSER_PASSWORD}'

u, created = User.objects.get_or_create(username=username, defaults={'email': email})
u.is_staff = True
u.is_superuser = True

if email and (u.email != email):
    u.email = email

u.set_password(password)
u.save()
print('superuser_ready', username)
"
fi

exec python manage.py runserver 0.0.0.0:8000
