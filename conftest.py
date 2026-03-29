"""
conftest.py
===========
pytest shared fixtures for the Automotive ECU Test Automation Framework.

Fixture scopes:
    session  — CANoe app startup/teardown  (once per full run)
    module   — UDS helper + session control per feature file
    function — ECU state reset before each individual test

Author : Rakesh Aragodi
"""

import os
import logging
import pytest

from utils.canoe_interface import CANoeInterface
from utils.uds_helper import UDSHelper
from utils.report_generator import ReportGenerator
from utils.xray_client import XrayClient

logger = logging.getLogger(__name__)

# ── Load .env if present (local dev only) ─────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CANOE_CONFIG = os.getenv("CANOE_CONFIG_PATH", r"C:\HIL\configs\BCM_SDV_Test.cfg")
JIRA_PLAN_KEY = os.getenv("JIRA_PLAN_KEY", "BCM-50")


# ══════════════════════════════════════════════════════════════════════
# SESSION-SCOPED — CANoe application (expensive: open once per run)
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def canoe(request):
    """
    Start CANoe, open the HIL config, run measurement.
    Shared across ALL tests in the session.
    Teardown: stop measurement and close app.
    """
    logger.info("=== SESSION SETUP: Starting CANoe ===")
    app = CANoeInterface()
    app.open(CANOE_CONFIG)
    app.start_measurement(stabilise_seconds=2.0)

    yield app

    logger.info("=== SESSION TEARDOWN: Stopping CANoe ===")
    app.stop_measurement()


# ══════════════════════════════════════════════════════════════════════
# SESSION-SCOPED — Report generator (collect results across all tests)
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def report_generator():
    """Shared report collector — results added per test, saved at end."""
    rg = ReportGenerator(project="JLR SDV BCM", build=None)
    yield rg
    # Save Excel report after all tests complete
    path = rg.save(output_dir="reports")
    logger.info("Excel report saved: %s", path)


# ══════════════════════════════════════════════════════════════════════
# MODULE-SCOPED — UDS helper (one diagnostic session per feature file)
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def uds(canoe):
    """
    UDS helper tied to the CANoe interface.
    Switches ECU to extended diagnostic session before the module runs,
    returns to default session after.
    """
    helper = UDSHelper(canoe)

    # Switch to extended session for full UDS access
    response = helper.session_control(0x03)
    if not response.is_positive:
        pytest.skip("Could not enter extended diagnostic session — skipping UDS module")

    logger.info("Module setup: ECU in extended diagnostic session (0x03)")
    yield helper

    # Return to default session
    helper.session_control(0x01)
    logger.info("Module teardown: ECU returned to default session (0x01)")


# ══════════════════════════════════════════════════════════════════════
# FUNCTION-SCOPED — ECU state reset before each test
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function", autouse=False)
def reset_bcm_state(canoe):
    """
    Reset BCM signals to known-good state before each test.
    Mark tests with @pytest.mark.usefixtures("reset_bcm_state") to apply.
    """
    logger.info("[SETUP] Resetting BCM signal state")
    canoe.set_signal_value("Comfort", "DoorControl", "DoorLock_Cmd", 0)
    canoe.set_signal_value("Chassis", "VehicleInfo", "VehicleSpeed_kph", 0)
    import time; time.sleep(0.2)

    yield

    logger.info("[TEARDOWN] BCM state reset complete")


@pytest.fixture(scope="function")
def clear_dtcs(uds):
    """Clear all ECU DTCs before and after each test."""
    uds.clear_dtc(group_of_dtc=0xFFFFFF)
    yield
    uds.clear_dtc(group_of_dtc=0xFFFFFF)


# ══════════════════════════════════════════════════════════════════════
# SESSION-SCOPED — Xray client (upload results at end of run)
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def xray():
    """Jira Xray client — used to upload results in CI post-processing."""
    return XrayClient()


# ══════════════════════════════════════════════════════════════════════
# Hooks
# ══════════════════════════════════════════════════════════════════════

def pytest_configure(config):
    """Register custom markers so pytest doesn't warn about unknown marks."""
    markers = [
        "smoke: fast, critical path tests — run first",
        "regression: full regression suite",
        "safety: functional safety related test cases",
        "dtc: DTC read/write/clear scenarios",
        "security: UDS security access tests",
        "fault_injection: tests that deliberately inject hardware faults",
        "data_driven: parametrized data-driven tests",
    ]
    for marker in markers:
        config.addinivalue_line("markers", marker)


def pytest_runtest_logreport(report):
    """Hook to log pass/fail to console in a clean automotive format."""
    if report.when == "call":
        status  = "PASS" if report.passed else "FAIL" if report.failed else "SKIP"
        outcome = "✅" if report.passed else "❌" if report.failed else "⚠️"
        logger.info("%s [%s] %s", outcome, status, report.nodeid)
