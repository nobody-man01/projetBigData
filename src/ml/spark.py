"""Création de la session Spark, commune à l'entraînement, au scoring temps réel et aux tests."""
import os
import sys

from pyspark.sql import SparkSession


def get_spark(app_name: str, master: str = "local[*]", conf: dict = None) -> SparkSession:
    """Session Spark ; en mode local, les processus Python de Spark utilisent le même Python que ce programme.

    Sans cela, une variable PYSPARK_PYTHON qui pointe vers un autre Python (autre environnement virtuel)
    provoque l'erreur PYTHON_VERSION_MISMATCH dès qu'un calcul passe par Python.
    """
    if master.startswith("local"):
        os.environ["PYSPARK_PYTHON"] = sys.executable
        os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
    builder = SparkSession.builder.appName(app_name).master(master)
    for key, value in (conf or {}).items():
        builder = builder.config(key, value)
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    return spark
