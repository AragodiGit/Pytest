"""
bcm_steps.py
============
Behave BDD step definitions for BCM (Body Control Module) feature files.

Implements Given/When/Then steps for:
    - features/bcm/door_lock.feature

Author : Rakesh Aragodi
"""

import time
from behave import given, when, then, step
from utils.canoe_interface import SignalTimeoutError


# ══════════════════════════════════════════════════════════════════════
# GIVEN — Preconditions
# ══════════════════════════════════════════════════════════════════════

@given('the BCM ECU is powered on and in default diagnostic session')
def step_bcm_powered_on(context):
    """Verify BCM is alive by reading a heartbeat signal."""
    heartbeat = context.canoe.get_signal_value(
        "Comfort", "BCM_Status", "BCM_Heartbeat"
    )
    assert heartbeat is not None, "BCM ECU heartbeat not detected — ECU may be off"
    context.logger.info("BCM ECU is live (heartbeat = %s)", heartbeat)


@given('the HIL bench is connected and measurement is running')
def step_hil_connected(context):
    """Assert CANoe measurement is active (set in environment fixture)."""
    assert context.canoe._measurement_running, \
        "CANoe measurement is not running — check HIL bench connection"


@given('the vehicle speed signal "{signal_name}" is set to {speed:d}')
def step_set_vehicle_speed(context, signal_name, speed):
    context.canoe.set_signal_value("Chassis", "VehicleInfo", signal_name, speed)
    time.sleep(0.1)
    context.logger.info("Set %s = %d kph", signal_name, speed)


@given('all doors are currently locked')
def step_all_doors_locked(context):
    """Send lock command and verify before test begins."""
    context.canoe.send_can_frame("Comfort", 0x321, bytes([0x01]))
    context.canoe.wait_for_signal(
        "Comfort", "DoorLockStatus", "DoorLock_Status_FL",
        expected_value=1, timeout_ms=1000
    )


@given('a CAN bus-off fault is injected on bus "{bus_name}"')
def step_inject_busoff(context, bus_name):
    context.canoe.set_system_variable("FaultInjection", f"CAN_BusOff_{bus_name}", 1)
    context.logger.info("CAN bus-off injected on %s", bus_name)
    context.injected_bus = bus_name


# ══════════════════════════════════════════════════════════════════════
# WHEN — Actions
# ══════════════════════════════════════════════════════════════════════

@when('a CAN frame is sent on bus "{network}" with ID {can_id} and data {payload}')
def step_send_can_frame(context, network, can_id, payload):
    """Send a raw CAN frame with hex ID and payload."""
    can_id_int  = int(can_id, 16)
    payload_int = int(payload, 16)
    data = bytes([payload_int])
    context.canoe.send_can_frame(network, can_id_int, data)
    context.logger.info(
        "Sent CAN frame — bus=%s ID=0x%03X data=0x%02X", network, can_id_int, payload_int
    )


@when('the CAN bus-off fault is cleared after {duration_ms:d} ms')
def step_clear_busoff(context, duration_ms):
    time.sleep(duration_ms / 1000.0)
    bus_name = getattr(context, "injected_bus", "Comfort")
    context.canoe.set_system_variable("FaultInjection", f"CAN_BusOff_{bus_name}", 0)
    context.logger.info("CAN bus-off cleared on %s after %d ms", bus_name, duration_ms)


# ══════════════════════════════════════════════════════════════════════
# THEN — Assertions
# ══════════════════════════════════════════════════════════════════════

@then('the BCM output signal "{signal_name}" should equal {expected:d} within {timeout:d} ms')
def step_assert_signal_value(context, signal_name, expected, timeout):
    try:
        context.canoe.wait_for_signal(
            network="Comfort",
            message="DoorLockStatus",
            signal=signal_name,
            expected_value=expected,
            timeout_ms=timeout,
        )
        context.logger.info(
            "PASS: Signal %s = %d (within %d ms)", signal_name, expected, timeout
        )
    except SignalTimeoutError as exc:
        context.logger.error("FAIL: %s", exc)
        raise AssertionError(str(exc)) from exc


@then('no DTC should be present in the BCM ECU')
def step_no_dtc(context):
    dtcs = context.uds.read_dtc_by_status_mask(status_mask=0x08)
    assert len(dtcs) == 0, (
        f"Unexpected DTCs found: {[d.code_hex for d in dtcs]}"
    )


@then('the DTC "{dtc_code}" should be present in the BCM ECU')
def step_dtc_present(context, dtc_code):
    expected_code = int(dtc_code, 16)
    dtcs = context.uds.read_dtc_by_status_mask(status_mask=0x08)
    codes = [dtc.code for dtc in dtcs]
    assert expected_code in codes, (
        f"DTC {dtc_code} not found in ECU. Present: {[hex(c) for c in codes]}"
    )


@then('the BCM ECU should re-initialise the CAN node within {timeout_ms:d} ms')
def step_ecu_reinitialise(context, timeout_ms):
    context.canoe.wait_for_signal(
        network="Comfort",
        message="BCM_Status",
        signal="BCM_Heartbeat",
        expected_value=1,
        timeout_ms=timeout_ms,
    )


@then('the BCM output signal "{signal_name}" should equal {expected:d} within {timeout_ms:d} ms')
def step_assert_signal_timeout(context, signal_name, expected, timeout_ms):
    context.canoe.wait_for_signal(
        "Comfort", "BCM_Status", signal_name, expected, timeout_ms
    )
