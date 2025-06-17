# S2 Testing and Certification Tool

<div align="center">
    <a href="https://s2standard.org"><img src="./Logo-S2.svg" width="200" height="200" /></a>
</div>
<br />

## Overview

The **S2 Testing and Certification Tool** is an open-source Python application designed to test and certify implementations of S2 CEMs and RMs that use the S2 WebSocket JSON implementation. The tool enables S2 developers to verify that their CEM or RM is compliant with the S2 specification and S2 WebSocket JSON.

The tool supports two modes of operation:

1. **Test Mode**: Run integration tests locally to validate S2 device implementations.
2. **Certify Mode**: Perform tests remotely on a secure server and generate cryptographically signed compliance certificates.

This project is developed with modularity and extensibility in mind, making it easy to add new test cases, control types, and communication protocols.

---

## Features

- **Integration Testing**: Test S2 devices locally or remotely to verify compliance with the S2 Specification and S2 WebSocket JSON.
- **Test both CEM and RM Implementations**: Test both Resource Manager (RM) and Customer Energy Manager (CEM) implementations.
- **Control Type Coverage**: Includes test scenarios for the following control types:
  - Not Controllable
  - Power Envelope Based Control (PEBC)
  - Fill Rate Based Control (FRBC)
- **Result Reporting**: Generate detailed test reports, including pass/fail status, logs, and compliance summaries.
- **Certification**: Generate cryptographically signed certificates for compliant implementations.
- **Extensibility**: Easily add new test cases, control types.

---

## Installation

### Prerequisites

- Python 3.11 or higher
- Docker (optional, for containerized deployment)
- [UV Package Manager](https://docs.astral.sh/uv/) (for running the tool)

### Clone the Repository

```bash
git clone https://github.com/flexiblepower/s2-certification-tool.git
cd s2-certification-tool
```

### Clone with Submodules

This repository uses a custom version of the S2-Python library, included as a Git submodule. To clone the repository with the submodule, run:

```bash
git submodule init
git submodule update --remote --merge
```

TODO: Remove this once the S2Python package is updated

---

## Usage Local

### Running the Tool

The tool is executed using the `uv` package manager. To run the tool you must provide a configuration file path as an argument. Optionally supply the `-l` flag which specifies a log file where all S2 messages will be saved.

#### Example Command

```bash
cd s2-self-cert
uv run src/s2selfcert/main.py config.yaml -l messages.log
```

### Configuration

The tool uses a YAML configuration file to define the parameters for testing and certification. Below is an example configuration file and an explanation of its fields.

#### Example Configuration File

```yaml
device_details:
  name: Some Device
  manufacturer: ABCD

mode: testing  # Options: 'testing' for local testing, 'certification' for Certify Mode

certification:
  uri: ws://localhost:8001/  # WebSocket URI for the Certification Server

connection:
  mode: server  # Options: 'server' or 'client'

  # Host and port must be supplied when in server mode
  host: 0.0.0.0  # Host address for the WebSocket server
  port: 8000     # Port for the WebSocket server

  # URI must be supplied when in client mode
  uri: wss://localhost:8000/websocket  # WebSocket URI for the S2 device

report:
  yaml: report.yaml  # Path to save the YAML report

  # If provided then a JUnit XML output is produce. Mainly for usage in GitLab CI.
  xml: report.xml    # Path to save the XML report
  xml_soft_fail_is_fail: true  # Treat soft failures as failures in the XML report

  include_test_parameters: false  # Whether to include test parameters in the report

roles:
  # Here you can enable or disable the RM or CEM testing or specific control types.
  # Any that are left blank will default to `enabled = true`
  rm:  # Resource Manager (RM) role configuration
    enabled: false 
    not_controllable:
        enabled: true
    pebc: 
      enabled: true
    frbc:
      enabled: true
  cem:  # Customer Energy Manager (CEM) role configuration
    enabled: true
    not_controllable:
      enabled: true
    pebc:
      enabled: true
      instruction_wait_timeout: 0
    frbc:
      enabled: true
      instruction_wait_timeout: 0
```

---

## Usage Server

### Running the tool

The server component of the tool is a FastAPI server that is executed using the `uv` package manager. Once the tool is running a client instance can connect in order to be tested and certified.

#### Example Command - Server

```bash
cd s2-self-cert-server
uv run fastapi dev ./src/main.py  --port 8000 --host 0.0.0.0
```

## Project Structure

The repository is organized into the following directories and files:

```text
.
├── packages                         # Shared Python packages
│   ├── connectivity                 # WebSocket communication logic
│   ├── s2-python                    # Custom version of the S2-Python library. TODO: Remove!
│   └── test-suites                  # Test suite logic
├── s2-self-cert                     # Client application
└── s2-self-cert-server              # Server application
```

The project is split into 4 python packages which are all managed by UV

---

## Architecture

The tool is built using a modular, object-oriented design. Key components include:

- **Connection Adapter**: Abstracts WebSocket communication, supporting both FastAPI and standard Python WebSocket implementations.
- **Test Suite**: Encapsulates test cases and orchestrates their execution.
- **Controllers**: Manage state and behavior for specific control types.
- **Client and Server Applications**: Facilitate local testing and remote certification.

---

### Adding support for a new New Control Type

---

### Adding New Test Cases

To add a new test case:

1. Implement a new `TestCase` class in the `testsuites` package under "./src/testsuites/test_suite"
    - Optionally, inherit from one of the existing base classes.
2. Register the new `TestCase` with the builder in the CEM or RM `builder.py` file.

This is a very simplified explanation. For more details see: **TODO**

---

## Future Plans

- Add support for additional control types (PPBC, DDBC, OMBC).
