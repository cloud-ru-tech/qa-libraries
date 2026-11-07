FROM python:3.13-slim

RUN pip install --no-cache-dir "grpcio==1.85.1" "protobuf==7.36.2"

WORKDIR /app
COPY service.py ./

EXPOSE 50051
CMD ["python", "service.py"]
