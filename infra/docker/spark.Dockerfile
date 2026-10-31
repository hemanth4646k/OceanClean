# Spark 3.5.1 on Java 17 with the Kafka connector baked in, so runtime needs no network.
FROM bitnamilegacy/spark:3.5.1
USER root
ADD https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.5.1/spark-sql-kafka-0-10_2.12-3.5.1.jar \
    https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_2.12/3.5.1/spark-token-provider-kafka-0-10_2.12-3.5.1.jar \
    https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.4.1/kafka-clients-3.4.1.jar \
    https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar \
    /opt/bitnami/spark/jars/
RUN cd /opt/bitnami/spark/jars \
 && chmod 644 spark-sql-kafka-0-10_2.12-3.5.1.jar spark-token-provider-kafka-0-10_2.12-3.5.1.jar \
      kafka-clients-3.4.1.jar commons-pool2-2.11.1.jar \
 && pip install --no-cache-dir "psycopg[binary]==3.2.3" "pydantic==2.10.4" "numpy==2.2.1" "pyarrow==18.1.0" "netCDF4==1.7.2" "pytest==8.3.4"
RUN mkdir -p /checkpoints && chown 1001:0 /checkpoints
USER 1001
# Spark's own python libs too, so plain `python -m pytest` can import pyspark.
ENV PYTHONPATH=/app/common:/app/routing:/app/streaming:/app/batch:/opt/bitnami/spark/python:/opt/bitnami/spark/python/lib/py4j-0.10.9.7-src.zip
