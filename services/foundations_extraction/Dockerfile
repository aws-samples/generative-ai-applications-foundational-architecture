FROM --platform=linux/amd64  python:3.9-alpine

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

RUN apk --no-cache add curl

EXPOSE 80

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]

