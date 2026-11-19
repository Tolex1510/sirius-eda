FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY delivery_service ./delivery_service
COPY delivery_pb2.py delivery_pb2_grpc.py ./
COPY alembic ./alembic
COPY alembic.ini ./
COPY docs/knowledge ./docs/knowledge
COPY deploy ./deploy
COPY data/menu ./data/menu
RUN useradd --create-home --uid 10001 sirius
USER sirius
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
