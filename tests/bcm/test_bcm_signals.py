"""
test_bcm_signals.py
===================
Parametrized pytest tests for BCM (Body Control Module) CAN signal validation.

Tests are driven by test vectors loaded from bcm_test_vectors.xlsx
and linked to Jira Xray test keys via xray_test_key property.

Author : Rakesh Aragodi
Xray Plan: BCM-50
"""

import time
import pytest
import pandas as pd

from utils.canoe_interface import SignalTimeoutError
from utils.report_generator import TestResultRow

# ── Load test vectors from Excel ───────────────────────────────────────
TEST_VECTORS_PATH = "test_data/bcm_test_vectors.xlsx"

try:
    _df = pd.read_excel(TEST_VECTORS_PATH, sheet_name="DoorLock")
    DOOR_LOCK_VECTORS = _df.to_dict("records")
except FileNotFoundError:
    # Fallback for CI without test data file
    DOOR_LOCK_VECTORS = [
        {
            "test_id"        : "BCM-TC-001",
            "xray_key"       : "BCM-101",
            "requirement"    : "BCM-REQ-012",
            "can_id"         : 0x321,
            "payload"        : 0x01,
            "signal_name"    : "DoorLock_Status_FL",
            "expected_value" : 1,
            "timeout_ms"     : 500,
            "description"    : "Standard door lock command",
        },
        {
            "test_id"        : "BCM-TC-002",
            "xray_key"       : "BCM-102",
            "requirement"    : "BCM-REQ-012",
            "can_id"         : 0x321,
            "payload"        : 0x00,
            "signal_name"    : "DoorLock_Status_FL",
            "expected_value" : 0,
            "timeout_ms"     : 500,
            "description"    : "Standard door unlock command",
        },
        {
            "test_id"        : "BCM-TC-003",
            "xray_key"       : "BCM-103",
            "requirement"    : "BCM-REQ-015",
            "can_id"         : 0x321,
            "payload"        : 0x0F,
            "signal_name"    : "DoorLock_Status_FL",
            "expected_value" : 1,
            "timeout_ms"     : 500,
            "description"    : "Lock all doors command",
        },
    ]


# ══════════════════════════════════════════════════════════════════════
# BCM Signal Tests
# ══════════════════════════════════════════════════════════════════════

class TestBCMDoorLock:
    """
    Body Control Module — door lock CAN signal validation.
    Each test case is driven by a row in bcm_test_vectors.xlsx.
    """

    @pytest.mark.regression
    @pytest.mark.parametrize(
        "vector",
        DOOR_LOCK_VECTORS,
        ids=[v["test_id"] for v in DOOR_LOCK_VECTORS],
    )
    @pytest.mark.usefixtures("reset_bcm_state")
    def test_door_lock_signal_response(
        self, vector, canoe, report_generator
    ):
        """
        Validate BCM door lock output signal against CAN command input.

        Given a CAN frame with the specified ID and payload is sent,
        the BCM output signal should reach the expected value within timeout.

        [xray_test_key] extracted from vector["xray_key"] for Xray upload.
        """
        # ── Arrange ──────────────────────────────────────────────────
        can_id       = vector["can_id"]
        payload      = bytes([vector["payload"]])
        signal_name  = vector["signal_name"]
        expected     = vector["expected_value"]
        timeout_ms   = int(vector["timeout_ms"])

        # ── Act ───────────────────────────────────────────────────────
        start = time.monotonic()
        canoe.send_can_frame(
            network="Comfort",
            can_id=can_id,
            data=payload,
        )

        # ── Assert ────────────────────────────────────────────────────
        try:
            canoe.wait_for_signal(
                network="Comfort",
                message="DoorLockStatus",
                signal=signal_name,
                expected_value=expected,
                timeout_ms=timeout_ms,
            )
            actual  = expected   # reached expected
            status  = "PASS"
            notes   = ""
        except SignalTimeoutError as exc:
            actual  = canoe.get_signal_value("Comfort", "DoorLockStatus", signal_name)
            status  = "FAIL"
            notes   = str(exc)
            pytest.fail(str(exc))
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            report_generator.add_result(TestResultRow(
                test_id      = vector["test_id"],
                test_name    = vector["description"],
                feature      = "BCM",
                status       = status,
                duration_ms  = duration_ms,
                requirement  = vector["requirement"],
                xray_key     = vector["xray_key"],
                signal_name  = signal_name,
                signal_value = actual if status == "PASS" else None,
                expected     = expected,
            ))


class TestBCMSpeedInhibit:
    """BCM speed-based lock inhibit — functional safety test cases."""

    @pytest.mark.safety
    @pytest.mark.regression
    @pytest.mark.parametrize("speed_kph,lock_cmd,should_lock", [
        (0,   0x01, True),     # Parked — lock allowed
        (10,  0x01, True),     # Low speed — lock allowed
        (50,  0x01, False),    # Medium speed — inhibited
        (120, 0x01, False),    # Highway — inhibited
    ])
    @pytest.mark.usefixtures("reset_bcm_state")
    def test_lock_inhibit_at_speed(
        self, speed_kph, lock_cmd, should_lock, canoe, report_generator
    ):
        """
        BCM must inhibit door lock commands when vehicle speed exceeds threshold.

        Requirement: BCM-REQ-021 — Door lock inhibit above 30 km/h.
        [xray_test_key: BCM-110]
        """
        # Set vehicle speed via simulation
        canoe.set_signal_value("Chassis", "VehicleInfo", "VehicleSpeed_kph", speed_kph)
        time.sleep(0.1)

        # Send lock command
        canoe.send_can_frame(
            network="Comfort",
            can_id=0x321,
            data=bytes([lock_cmd]),
        )

        # Assert signal
        expected_lock_status = 1 if should_lock else 0
        test_id = f"BCM-TC-SPEED-{speed_kph}"

        try:
            canoe.wait_for_signal(
                network="Comfort",
                message="DoorLockStatus",
                signal="DoorLock_Status_FL",
                expected_value=expected_lock_status,
                timeout_ms=700,
            )
            status = "PASS"
        except SignalTimeoutError as exc:
            status = "FAIL"
            pytest.fail(f"Speed={speed_kph} kph — {exc}")
        finally:
            report_generator.add_result(TestResultRow(
                test_id     = test_id,
                test_name   = f"Lock inhibit at {speed_kph} kph",
                feature     = "BCM",
                status      = status,
                duration_ms = 700,
                requirement = "BCM-REQ-021",
                xray_key    = "BCM-110",
            ))


class TestBCMFaultInjection:
    """BCM fault injection — CAN bus-off recovery validation."""

    @pytest.mark.fault_injection
    @pytest.mark.regression
    def test_can_busoff_recovery(self, canoe, report_generator):
        """
        Inject a CAN bus-off fault and verify BCM recovers within 5 seconds.

        Requirement: BCM-REQ-030
        [xray_test_key: BCM-120]
        """
        # Inject fault via system variable
        canoe.set_system_variable("FaultInjection", "CAN_BusOff_Comfort", 1)
        time.sleep(2.0)   # Bus-off duration

        # Clear fault
        canoe.set_system_variable("FaultInjection", "CAN_BusOff_Comfort", 0)

        # ECU should recover
        try:
            canoe.wait_for_signal(
                network="Comfort",
                message="BCM_Status",
                signal="CAN_BusOff_Flag",
                expected_value=0,
                timeout_ms=5000,
            )
            status = "PASS"
        except SignalTimeoutError as exc:
            status = "FAIL"
            pytest.fail(f"BCM did not recover from bus-off: {exc}")
        finally:
            report_generator.add_result(TestResultRow(
                test_id     = "BCM-TC-FAULT-001",
                test_name   = "CAN bus-off recovery",
                feature     = "BCM",
                status      = status,
                duration_ms = 5000,
                requirement = "BCM-REQ-030",
                xray_key    = "BCM-120",
            ))
