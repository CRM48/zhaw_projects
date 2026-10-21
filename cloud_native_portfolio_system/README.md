# Cloud-Native Portfolio Decision Support — System Design and Evaluation

A research and experimental project investigating cloud-native architectures for an agentic AI portfolio decision-support system. Developed as part of the Master of Science in Engineering at ZHAW.

The project establishes the system requirements, reviews relevant technologies, and evaluates different deployment architectures to inform the design of a larger master's thesis project. The main focus is on how architectural choices affect performance of the system on a component and system-wide level.

## Experiments

The project includes four experiments implemented using Python services, Docker, and supporting workload-generation scripts.

### 1. Monolith vs Microservices

Compares two approaches to processing portfolio recommendation requests:

- **Monolith:** Executes the request-processing, portfolio-generation, and evaluation stages within a single service.
- **Microservices:** Separates these stages into independently deployed services communicating over HTTP.

Measures request latency and throughput under different concurrency levels to evaluate the overhead of distributing application components.

### 2. Direct vs Event-Driven Processing

Investigates two approaches to processing market-data updates:

- **Direct:** Market-data events are sent directly to an API for processing.
- **Event-driven:** Events are published through NATS and processed asynchronously by consumers.

Examines throughput, processing latency, and scaling behaviour under different workload sizes and consumer configurations.

### 3. Workload Isolation

Evaluates how simultaneous user requests and background market-data processing affect overall system performance.

The experiment combines the workloads from Experiments 1 and 2 to investigate resource contention and the effects of separating workloads through deployment and resource-allocation strategies.

### 4. Serverless Suitability

Investigates whether serverless deployment is appropriate for intermittently used portfolio-processing services.

A portfolio-evaluation service is subjected to idle periods followed by bursts of requests. The experiment compares continuously running and serverless deployments, focusing on response latency, cold-start overhead, and resource efficiency.

## Project Structure

```text
cloud_native_portfolio_system/
├── compose/                 # Docker Compose configurations
├── data/                    # Synthetic market and user-request datasets
├── helpers/                 # Workload generators and testing utilities
├── src/
│   ├── common/              # Shared models, configuration, and results
│   ├── md_pipeline/         # Market-data processing services
│   ├── storage/             # Market signal storage
│   └── ur_pipeline/         # User-request and portfolio services
├── Dockerfile
├── requirements.txt
├── requirements-lock.txt
└── project_report.pdf
```

## Running the Experiments

### Requirements

- Docker and Docker Compose
- Python 3.12 (for running scripts outside Docker)

### Setup

From the project directory, build the Docker image:

```bash
docker build -t vt-experiments:local .
```

Each experiment has a separate Docker Compose configuration.

### Experiment 1 — Monolith vs Microservices

Start the services:

```bash
docker compose -f compose/experiment1.yml up -d
```

Run the workload generator:

```bash
docker compose -f compose/experiment1.yml run --rm user-load --architecture monolith
```

Replace `monolith` with `microservices` to test the alternative architecture.

### Experiment 2 — Market-Data Processing

Start the services:

```bash
docker compose -f compose/experiment2.yml up -d
```

Run a direct-processing workload:

```bash
docker compose -f compose/experiment2.yml run --rm runner python -m helpers.market_replayer --dataset-size small --architecture direct
```

Replace `direct` with `event` to test event-driven processing. The event-driven setup requires NATS stream configuration, provided by `helpers/setup_nats.py`.

### Experiment 3 — Workload Isolation

Start the services:

```bash
docker compose -f compose/experiment3.yml up -d
```

Run a combined workload:

```bash
docker compose -f compose/experiment3.yml run --rm runner python -m helpers.workload_isolation_runner --user-architecture monolith --market-architecture direct
```

The runner supports alternative user-request and market-data architectures.

### Experiment 4 — Serverless Suitability

Start the local portfolio-evaluation service:

```bash
docker compose -f compose/experiment4.yml up -d
```

Run the burst generator:

```bash
docker compose -f compose/experiment4.yml run --rm runner python -m helpers.serverless_burst_generator
```

The local deployment provides a continuously running baseline. Reproducing the serverless comparison requires a separate serverless deployment.

### Results and Cleanup

Experiment outputs are saved to the `results/` directory, which is excluded from Git.

To stop an experiment:

```bash
docker compose -f compose/experiment1.yml down
```

Replace `experiment1.yml` with the relevant configuration file.

## Project Report

The full [project report](project_report.pdf) contains the system specification, literature review, experimental methodology and findings, proposed architecture, and evaluation plan.

The experiments were originally conducted in a controlled cloud environment. The repository includes the application code, local Docker configurations, datasets, and workload generators, but not all original Kubernetes deployment configurations.

## Background

Developed as part of a master's thesis preparation project at the **ZHAW School of Engineering**, focusing on cloud-native systems, distributed architectures, and systems performance.

The project provides the architectural and experimental foundation for a subsequent thesis implementing and evaluating a cloud-native agentic AI portfolio decision-support system.