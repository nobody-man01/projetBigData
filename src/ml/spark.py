"""Création de la session Spark, commune à l'entraînement, au scoring temps réel et aux tests."""
import os
import socket
import sys

from pyspark.sql import SparkSession

from config.settings import SPARK_MASTER


def get_spark(app_name: str, master: str = None, conf: dict = None) -> SparkSession:
    """Session Spark, en local ou sur le cluster selon SPARK_MASTER (config/settings.py).

    En local, les processus Python de Spark utilisent le même Python que ce programme : sans cela, une
    variable PYSPARK_PYTHON pointant vers un autre environnement provoque PYTHON_VERSION_MISMATCH.
    Sur le cluster, les executors (dans les workers) doivent pouvoir rappeler le driver par son nom d'hôte.
    """
    master = master or SPARK_MASTER
    if master.startswith("local"):
        os.environ["PYSPARK_PYTHON"] = sys.executable
        os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
    builder = SparkSession.builder.appName(app_name).master(master)
    if not master.startswith("local"):
        builder = builder.config("spark.driver.host", socket.gethostname())
    for key, value in (conf or {}).items():
        builder = builder.config(key, value)
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark
