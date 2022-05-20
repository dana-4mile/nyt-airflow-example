FROM apache/airflow:2.3.0
USER root
RUN mkdir -p /var/local/gcs_keyfile
USER airflow
RUN pip install --no-cache-dir requests
RUN pip install --no-cache-dir pendulum
RUN pip install --no-cache-dir google-cloud-storage
