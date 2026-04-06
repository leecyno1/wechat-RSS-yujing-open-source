FROM docker.m.daocloud.io/library/python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY mcp_server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY mcp_server/server.py /app/server.py

EXPOSE 8090

CMD ["python", "/app/server.py"]
