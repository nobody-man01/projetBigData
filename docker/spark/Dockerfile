# Image commune au master, aux workers et au driver (spark-app) du cluster Spark.
# Même version de Spark et de Python partout : condition pour que driver et executors se comprennent.
FROM apache/spark:4.2.0-python3

USER root
# Dépendances Python du projet utiles côté Spark (lecture des CSV, écriture MongoDB, configuration)
COPY spark-defaults.conf /opt/spark/conf/spark-defaults.conf
RUN pip install --no-cache-dir "pandas>=2.0,<3" "numpy>=1.26" "pymongo>=4.6" "python-dotenv>=1.0"

# L'utilisateur spark prend l'identifiant de l'utilisateur de la machine hôte : le modèle, les profils
# et les checkpoints écrits dans le dossier du projet (monté en volume) lui appartiennent.
ARG HOST_UID=1000
ARG HOST_GID=1000
RUN groupmod -o -g ${HOST_GID} spark && usermod -o -u ${HOST_UID} -g ${HOST_GID} -d /home/spark spark \
    && mkdir -p /home/spark/.ivy2 /opt/spark/work /opt/spark/logs \
    && chown -R spark:spark /home/spark /opt/spark/work-dir /opt/spark/work /opt/spark/logs
ENV HOME=/home/spark \
    PYTHONPATH=/opt/spark/python:/opt/spark/python/lib/py4j-0.10.9.9-src.zip \
    PYSPARK_PYTHON=python3
USER spark
WORKDIR /app
