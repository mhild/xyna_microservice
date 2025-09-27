FROM python:3.13-slim
WORKDIR /app
COPY xyna-operator.py .
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["kopf", "run", "xyna-operator.py", "--standalone"]
