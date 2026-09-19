FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY README.md .
COPY oss_contribution_finder.py .

RUN pip install --no-cache-dir .

ENTRYPOINT ["oss-contribution-finder"]

