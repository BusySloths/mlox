# mlox

[![Logo](https://github.com/nicococo/mlox/blob/main/mlox/resources/mlox_logo_wide.png)](Logo)

MLOps-in-a-Box: A simple and cost-efficient way of running your OSS MLOps stack.



[![Maintainability](https://qlty.sh/badges/f6765ee4-a13b-4106-8ba2-236cfa251443/maintainability.svg)](https://qlty.sh/gh/nicococo/projects/mlox)

[![Code Coverage](https://qlty.sh/badges/f6765ee4-a13b-4106-8ba2-236cfa251443/test_coverage.svg)](https://qlty.sh/gh/nicococo/projects/mlox)


### ATTENTION

Do **not** use MLOX yet.
MLOX is in a very early development phase.

### About

Machine Learning (ML) and Artificial Intelligence (AI) are revolutionizing businesses and industries. Despite its importance, many companies struggle to go from ML/AI prototype to production.

ML/AI systems consist of eight non-trivial sub-problems: data collection, data processing, feature engineering, data labeling, model design, model training and optimization, endpoint deployment, and endpoint monitoring. Each of these step require specialized expert knowledge and specialized software. 

MLOps, short for **Machine Learning Operations,** is a paradigm that aims to tackle those problems and deploy and maintain machine learning models in production reliably and efficiently. The word is a compound of "machine learning" and the continuous delivery practice of DevOps in the software field.

Cloud provider such as Google Cloud Platform or Amazon AWS offer a wide range of solutions for each of the MLOps steps. However, solutions are complex and costs are notorious hard to control on these platforms and are prohibitive high for individuals and small businesses such as startups and SMBs. E.g. a common platform for data ingestion is Google Cloud Composer who’s monthly base rate is no less than 450 Euro for a meager 2GB RAM VPS. Solutions for model endpoint hosting are often worse and often cost thousands of euros p. month (cf. Databricks).

Interestingly, the basis of many cloud provider MLOps solutions is widely available open source software (e.g. Google Cloud Composer is based on Apache Airflow). However, these are  complex software packages were setup, deploy and maintaining is a non-trivial task.

This is were the MLOX project comes in. The goal of MLOX is four-fold:

1. [Infrastructure] MLOX offers individuals, startups, and small teams easy-to-use UI to securily deploy, maintain, and monitor complete MLOps infrastructures on-premise based on open-source software without any vendor lock-in.
2. [Code] To bridge the gap between the users` code base and the MLOps infrastructure,  MLOX offers a Python PYPI package that adds necessary functionality to integrate with all MLOps services out-of-the-box. 
3. [Processes] MLOX provides fully-functional templates for dealing with data from ingestion, transformation, storing, model building, up until serving.
4. [Migration] Scripts help to easily migrate parts of your MLOps infrastructure to other service providers.

Links:

1. https://en.wikipedia.org/wiki/MLOps
2. https://www.databricks.com/glossary/mlops
3. https://martinfowler.com/articles/cd4ml.html

--------