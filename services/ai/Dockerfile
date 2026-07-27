FROM python:3.11-slim

WORKDIR /app

# pyproject declares `packages = ["app"]` and `readme = "README.md"`, so both must
# exist before the install: with only pyproject.toml present, setuptools fails
# with "package directory 'app' does not exist" and the image cannot be built.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
