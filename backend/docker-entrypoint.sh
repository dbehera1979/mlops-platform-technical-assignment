set -e
echo "Running database migrations..."
python -m alembic upgrade head
echo "Migrations complete. Starting application..."
exec "$@"
