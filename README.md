## BusySloths presents

[![Logo](https://github.com/BusySloths/mlox/blob/main/mlox/resources/mlox_logo_wide.png?raw=true)](Logo)

<p align="center">
<strong>
Accelerate your ML journey—deploy production-ready MLOps in minutes, not months.
</strong>
</p>

Tired of tangled configs, YAML jungles, and broken ML pipelines? So were we.
MLOX gives you a calm, streamlined way to deploy, monitor, and maintain production-grade MLOps infrastructure—without rushing.
It’s for engineers who prefer thoughtful systems over chaos. Powered by sloths. Backed by open source.

<p align="center">
<a href="https://qlty.sh/gh/BusySloths/projects/mlox" target="_blank"><img src="https://qlty.sh/gh/BusySloths/projects/mlox/maintainability.svg" alt="Maintainability" /></a>
<a href="https://qlty.sh/gh/BusySloths/projects/mlox" target="_blank"><img src="https://qlty.sh/gh/BusySloths/projects/mlox/coverage.svg" alt="Code Coverage" /></a>
<a href="https://github.com/BusySloths/mlox/issues" target="_blank">
<img alt="GitHub Issues or Pull Requests" src="https://img.shields.io/github/issues/busysloths/mlox"></a>
<a href="https://github.com/BusySloths/mlox/discussions" target="_blank">
<img alt="GitHub Discussions" src="https://img.shields.io/github/discussions/busysloths/mlox"></a>
</p>

### ATTENTION

MLOX is still in a very early development phase. If you like to contribute in any capacity, we would love to hear from you `contact[at]mlox.org`.

### What Can You Do With MLOX?

#### Infrastructure

- Add, delete, tag and name server
- Select Native, Docker, Kubernetes backend
- Setup one or more single- or multi-node Kubernetes Cluster

#### Services

- Add, delete, and update Services
- Use a centralized secret and configuration manager out-of-the-box
- Install secured Docker Services (e.g. MLFlow, Airflow, LiteLLM, Ollama, InfluxDB, Redis, etc pp)
- Install K8s Services (e.g. Dashboard, Helm, Headlamp)
- Easily import public or private Github repositories
- Use the following GCP services in your code:
  - BigQuery
  - Secret Manager
  - Storage
  - and Spreadsheets

### Installation

There are two parts of the project.

#### A Web UI to Manage Your Infrastructure and Services

If you want to install the main UI to manage your infrastructure, then

```
  pip install busysloths-mlox[all]
```

and start the UI via

```
  mlox ui
```

This will install the main UI together with all supporting components (means lots of packages).

#### Utilize Your Infrastructure in Your Code

If you have existing MLOX infrastructure and want to use certain functionality in your apps, you can install only the necessary parts, e.g. if you want to use GCP related functionality:

```
  pip install busysloths-mlox[gcp]
```

This will only install the base packages as well as GCP related packages.

### Unnecessary Long Introduction

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

More Links:

1. <https://en.wikipedia.org/wiki/MLOps>
2. <https://www.databricks.com/glossary/mlops>
3. <https://martinfowler.com/articles/cd4ml.html>

## Contributing

### Sloth-Friendly Setup

Easing into MLOX should feel like a lazy stretch on a sunny branch:

1. Install [Task](https://taskfile.dev/installation/) – our go-powered task runner.
2. Clone this repository.
3. Mosey into the project and run:

   ```bash
   task first:steps
   ```

   This unhurried command crafts a conda environment and gathers every dependency for you.

Once you're comfortably set up, there are many ways to contribute, and they are not limited to writing code. We welcome all contributions such as:

- <a href="https://github.com/BusySloths/mlox/issues/new/choose">Bug reports</a>
- <a href="https://github.com/BusySloths/mlox/issues/new/choose">Documentation improvements</a>
- <a href="https://github.com/BusySloths/mlox/issues/new/choose">Enhancement suggestions</a>
- <a href="https://github.com/BusySloths/mlox/issues/new/choose">Feature requests</a>
- <a href="https://github.com/BusySloths/mlox/issues/new/choose">Expanding the tutorials and use case examples</a>

Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## Big Thanks to our Sponsors

MLOX is proudly funded by the following organizations:

<img src="https://github.com/BusySloths/mlox/blob/main/mlox/resources/BMFTR_logo.jpg?raw=true" alt="BMFTR" width="420px"/>

## Supporters

We would not be here without the generous support of the following people and organizations:

<p align="center">
<img src="https://github.com/BusySloths/mlox/blob/main/mlox/resources/PrototypeFund_logo_light.png?raw=true" alt="PrototypeFund" width="380px"/>
<img src="https://github.com/BusySloths/mlox/blob/main/mlox/resources/PrototypeFund_logo_dark.png?raw=true" alt="PrototypeFund" width="380px"/>
</p>

## License  

MLOX is open-source and intended to be a community effort, and it wouldn't be possible without your support and enthusiasm.
It is distributed under the terms of the MIT license. Any contribution made to this project will be subject to the same provisions.

## Join Us

We are looking for nice people who are invested in the problem we are trying to solve.
