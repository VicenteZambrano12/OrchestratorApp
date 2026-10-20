# Orchestrator App Repo

An agentic AI system connected to a SQL database that demonstrates how modern AI applications work and how natural-language queries can be routed to different integrated AI systems based on user intent.

## 1. Overview

Modern general-purpose AI chat applications, such as ChatGPT, Gemini, and Claude, can bring multiple AI capabilities and systems together in a single conversational interface. A key part of this experience is routing each user's request to the appropriate system based on their intent.

In this project, we call the component responsible for that routing the **orchestrator**. Using a list of available AI systems and capabilities, the orchestrator relies on a large language model (LLM) to decide where to send each query.

Although orchestration can become complex, this project presents a simple architecture and design, showing how an orchestrator can be integrated into an application for a realistic use case.

The project also includes:

- **A React frontend** with a chat interface and a button that lets users inspect what happens behind the scenes to understand how the system works.
- **A Terraform module** for provisioning the proposed Google Cloud Platform (GCP) infrastructure, including a virtual machine, databases, and secrets.
- **A deployment workflow** designed for a production environment, with pull request checks for changes coming from a development branch. To reduce costs for demonstration purposes, development runs locally rather than in a separate cloud environment.

Feel free to clone this repository and use it as a starting point for your own project.

## 2. Business Overview, Use Case, and Value

The selected use case is **Form**, a gym application. Fitness is a familiar topic for many people, making the example easy to understand and its underlying patterns easy to apply to other business needs.

Form lets users interact with a virtual fitness trainer through a chatbot and record their workout progress. The chatbot supports three tasks:

1. **Explain an exercise**, using exercise information and reference images.
2. **Create a workout routine**.
3. **Show the user's progress**, helping them review past workouts.

These tasks address common needs for gym users: planning routines, following them during training, reviewing previous workouts to support progressive overload, and clarifying how to perform exercises. And yes, this use case was inspired by being a gym rat.

### How the Use Case Works

The application combines an orchestrator, a SQL database storing users, routines, exercises, and workout records, and an image repository containing exercise illustrations.

The orchestrator identifies which of the three supported tasks matches the user's intent and routes the request to the appropriate specialized agent. That agent carries out the task under strict instructions, with observability measures and controlled database access. Rather than generating arbitrary SQL, agents supply parameters to predefined SELECT queries to retrieve the information they need.

Users can also access their saved routines directly in the **Routines** tab. The application uses the information stored in the database to present routines and workout records through a structured interface, not just through chat.

### Business Value

Although Form focuses on fitness, the same approach can be applied to many business scenarios:

- **Focused AI assistance:** support a defined set of business tasks rather than an unrestricted chatbot.
- **Intent-based routing:** direct each request to the agent or system responsible for that task.
- **Controlled data retrieval:** retrieve database information through predefined, parameterized queries, reducing the risk of incorrect queries.
- **Structured data presentation:** make stored information available through a clear application interface as well as conversational responses.
- **Access to unstructured resources:** retrieve supporting assets, such as images, from repositories outside the relational database.
- **Extensibility and observability:** incorporate additional AI systems over time while maintaining strict observability across routing decisions and task execution.
- **Infrastructure as Code (IaC):** define infrastructure in version-controlled code to support collaboration and repeatable deployments across environments.

## 3. Repository Structure

The application is organized into three main modules: **infra**, **backend**, and **frontend**. A supporting **database** directory includes a SQLite database and its schema, while **scripts** contains utilities for migrating database data and exercise images. The deployment workflow lives in **.github/workflows**.

The following tree highlights the main directories and files; individual source files and supporting assets are omitted for readability.

```text
OrchestratorApp/
|-- .github/
|   `-- workflows/
|       `-- terraform-deploy.yml     # Infrastructure and deployment workflow
|-- backend/
|   |-- src/                        # API, orchestration, and AI system implementation
|   |-- tests/                      # Backend tests
|   `-- pyproject.toml              # Backend dependencies and configuration
|-- frontend/
|   |-- public/                     # Public assets
|   |-- src/                        # React application
|   |-- tests/                      # Frontend browser tests
|   `-- package.json                # Frontend dependencies and commands
|-- infra/
|   |-- environments/
|   |   `-- prod/                   # Production Terraform configuration
|   |-- modules/
|   |   |-- artifact_registry/
|   |   |-- cloudrun/
|   |   |-- database/
|   |   |-- secrets/
|   |   `-- storage/
|   `-- scripts/                    # Infrastructure access bootstrap scripts
|-- database/
|   |-- database_schema.json        # Database schema reference
|   `-- gym_app.db                  # SQLite database
|-- scripts/
|   |-- migrate_database.py         # Database migration utility
|   |-- migrate_images.py           # Exercise image migration utility
|   `-- registry_images.py          # Exercise image registration utility
|-- src/
|   `-- orchestratorapp/            # Root Python package
|-- .env.example                    # Example environment configuration
|-- Dockerfile                      # Container image definition
|-- pyproject.toml                  # Root Python project configuration
|-- uv.lock                         # Root Python dependency lockfile
`-- README.md
```