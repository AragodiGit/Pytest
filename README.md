# 🚗 Automotive ECU Test Automation Framework

> **Python BDD automation framework for BCM and UDS ECU validation**  
> Built for HIL (Hardware-in-the-Loop) test environments using dSPACE & Vector CANoe

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![pytest](https://img.shields.io/badge/pytest-7.x-0A9EDC?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org)
[![Behave](https://img.shields.io/badge/BDD-Behave-00B388?style=flat-square)](https://behave.readthedocs.io)
[![GitLab CI](https://img.shields.io/badge/CI%2FCD-GitLab-FC6D26?style=flat-square&logo=gitlab&logoColor=white)](https://gitlab.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## 📌 Overview

This framework validates **Body Control Module (BCM)** and **UDS Diagnostic** ECU behaviour on a dSPACE HIL bench using Vector CANoe. Tests are written in **Gherkin (BDD)**, executed via **pytest + Behave**, and results are automatically reported to **Jira Xray** with Excel summary reports generated via **openpyxl/pandas**.

### Key Metrics (JLR SDV Program)
| Metric | Result |
|---|---|
| Test cases automated | 500+ |
| Coverage improvement | +40% |
| Manual reporting effort reduced | 35% |
| Critical defects caught pre-integration | 20+ |

---

## 🏗️ Project Structure

```
automotive_pytest_showcase/
│
├── features/                    # Gherkin BDD feature files
│   ├── bcm/
│   │   └── door_lock.feature    # BCM door lock scenarios
│   └── uds/
│       └── diagnostics.feature  # UDS diagnostic service scenarios
│
├── steps/                       # Python step definitions
│   ├── bcm_steps.py             # BCM step implementations
│   ├── uds_steps.py             # UDS step implementations
│   └── common_steps.py          # Shared steps (setup/teardown)
│
├── utils/                       # Core utility modules
│   ├── canoe_interface.py       # Vector CANoe COM API wrapper
│   ├── uds_helper.py            # UDS service builder & parser
│   ├── report_generator.py      # Excel report via openpyxl/pandas
│   └── xray_client.py           # Jira Xray REST API integration
│
├── tests/                       # pytest standalone tests
│   ├── bcm/
│   │   └── test_bcm_signals.py  # Parametrized BCM signal tests
│   └── uds/
│       └── test_uds_services.py # UDS service validation tests
│
├── test_data/
│   ├── bcm_test_vectors.xlsx    # BCM signal input/expected values
│   └── uds_service_config.json  # UDS service IDs and parameters
│
├── reports/                     # Auto-generated test reports (gitignored)
│
├── conftest.py                  # Session/module fixtures
├── pytest.ini                   # pytest configuration & markers
├── behave.ini                   # Behave configuration
├── requirements.txt             # Python dependencies
└── .gitlab-ci.yml               # GitLab CI/CD pipeline
```

---

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.10+
- Vector CANoe 17+ (with COM server enabled)
- dSPACE ControlDesk / AutomationDesk (for HIL runs)
- Jira account with Xray plugin (for reporting)

### Install
```bash
git clone https://github.com/AragodiGit/automotive-pytest-showcase.git
cd automotive-pytest-showcase
pip install -r requirements.txt
```

### Configure environment
```bash
cp .env.example .env
# Edit .env with your CANoe config path, Jira credentials, etc.
```

---

## 🚀 Running Tests

```bash
# Run all BDD scenarios
behave features/

# Run specific feature
behave features/bcm/door_lock.feature

# Run only smoke-tagged scenarios
behave --tags=@smoke

# Run pytest parametrized tests
pytest tests/ -v --tb=short

# Run with JUnit XML for CI
pytest tests/ --junitxml=reports/results.xml -v

# Run BCM regression suite
pytest tests/bcm/ -m regression -v

# Run with HTML report
pytest tests/ --html=reports/report.html --self-contained-html
```

---

## 🔁 CI/CD Pipeline

The GitLab CI pipeline runs automatically on every push and on a nightly schedule:

1. **Lint** — flake8 + black check
2. **Unit tests** — fast mock-based tests (no hardware needed)
3. **Regression** — full HIL test run (scheduled, hardware runner)
4. **Report** — Excel + Xray upload
5. **Notify** — Slack alert on failure

See [`.gitlab-ci.yml`](.gitlab-ci.yml) for full pipeline config.

---

## 📊 Test Reporting

After each run, two reports are generated automatically:

- **Excel report** — `reports/test_report_<timestamp>.xlsx` with pass/fail, signal values, timestamps
- **Jira Xray** — test execution results uploaded via REST API, linked to requirements

---

## 👤 Author

**Rakesh Aragodi** — HIL & Test Automation Engineer  
[LinkedIn](https://linkedin.com/in/rakesharagodi) · [GitHub](https://github.com/AragodiGit) · rakesharagodi@gmail.com
