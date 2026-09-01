FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
COPY pyproject.toml ./
COPY loan_rules ./loan_rules
COPY data ./data
COPY fnma_sf ./fnma_sf
COPY backend ./backend
RUN pip install --no-cache-dir -e ".[backend]"
# produce the seed package (users.json + graded tape) inside the image
RUN python -m data.generate --rows 1000 --seed 1234 --out-dir data
EXPOSE 8080
# Bind to $PORT when the platform sets one (Cloud Run injects 8080); default 8080 for
# local docker-compose. Shell form so ${PORT} is expanded; exec so uvicorn is PID 1.
CMD ["sh", "-c", "exec python -m uvicorn backend.app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}"]
