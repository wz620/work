FROM python:3.12.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY backend/requirements.lock.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && useradd --uid 10001 --create-home course
COPY deployment/requirements.lock.txt /tmp/deployment-requirements.txt
RUN pip install --no-cache-dir -r /tmp/deployment-requirements.txt
COPY backend/ backend/
COPY recommender/ recommender/
COPY scripts/student_package.py scripts/student_package.py
COPY deployment/*.py deployment/
USER 10001
EXPOSE 8000
ENTRYPOINT ["python", "-m", "deployment.serve"]
