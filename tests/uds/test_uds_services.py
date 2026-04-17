"""
test_uds_services.py
====================
Parametrized pytest tests for UDS diagnostic service validation.
Covers session control, ReadDID, SecurityAccess, DTC read/clear, ECU reset.

Author : Rakesh Aragodi
Xray Plan: BCM-50
"""

import time
import pytest

from utils.uds_helper import UDSHelper, SERVICE
from utils.report_generator import TestResultRow


# ══════════════════════════════════════════════════════════════════════
# Session Control (0x10)
# ══════════════════════════════════════════════════════════════════════

class TestUDSSessionControl:
    """UDS 0x10 DiagnosticSessionControl — all session types."""

    @pytest.mark.smoke
    @pytest.mark.parametrize("session_type,session_name", [
        (0x01, "Default"),
        (0x02, "Programming"),
        (0x03, "Extended Diagnostic"),
    ])
    def test_session_switch(self, session_type, session_name, uds, report_generator):
        """
        ECU must respond positively to all standard session control requests.

        Requirement: UDS-REQ-001
        [xray_test_key: UDS-201]
        """
        response = uds.session_control(session_type)

        assert response.is_positive, (
            f"Session 0x{session_type:02X} ({session_name}) rejected: "
            f"NRC=0x{response.nrc:02X} [{response.nrc_description}]"
        )
        assert response.sub_function == session_type, (
            f"Response sub-function mismatch: "
            f"got 0x{response.sub_function:02X}, expected 0x{session_type:02X}"
        )

        report_generator.add_result(TestResultRow(
            test_id    = f"UDS-TC-0x10-{session_type:02X}",
            test_name  = f"Session control — {session_name}",
            feature    = "UDS",
            status     = "PASS",
            duration_ms = 200,
            requirement = "UDS-REQ-001",
            xray_key   = "UDS-201",
        ))

        # Return to default session after each test
        uds.session_control(0x01)


# ══════════════════════════════════════════════════════════════════════
# ReadDataByIdentifier (0x22)
# ══════════════════════════════════════════════════════════════════════

class TestUDSReadDID:
    """UDS 0x22 ReadDataByIdentifier — standard DIDs."""

    @pytest.mark.smoke
    @pytest.mark.parametrize("did,did_name,min_length", [
        (0xF186, "ActiveDiagnosticSession",  1),
        (0xF187, "VehicleManufacturerSparePartNumber", 10),
        (0xF189, "ECUSoftwareVersionNumber",  4),
        (0xF18C, "ECUSerialNumber",           8),
        (0xF190, "VehicleIdentificationNumber", 17),
    ])
    def test_read_did(self, did, did_name, min_length, uds, report_generator):
        """
        ECU must return valid data for all standard DIDs.

        Requirement: UDS-REQ-010
        [xray_test_key: UDS-210]
        """
        response = uds.read_data_by_identifier(did)

        assert response.is_positive, (
            f"DID 0x{did:04X} ({did_name}) read failed: "
            f"NRC=0x{response.nrc:02X} [{response.nrc_description}]"
        )
        assert len(response.payload) >= min_length, (
            f"DID 0x{did:04X} response too short: "
            f"got {len(response.payload)} bytes, expected >= {min_length}"
        )

        report_generator.add_result(TestResultRow(
            test_id    = f"UDS-TC-0x22-{did:04X}",
            test_name  = f"ReadDID — {did_name}",
            feature    = "UDS",
            status     = "PASS",
            duration_ms = 150,
            requirement = "UDS-REQ-010",
            xray_key   = "UDS-210",
            notes      = f"payload={response.payload.hex()}",
        ))


# ══════════════════════════════════════════════════════════════════════
# SecurityAccess (0x27)
# ══════════════════════════════════════════════════════════════════════

class TestUDSSecurityAccess:
    """UDS 0x27 SecurityAccess — seed/key exchange."""

    @pytest.mark.regression
    @pytest.mark.security
    def test_security_access_valid_key(self, uds, report_generator):
        """
        ECU must grant access when the correct key is provided.

        Requirement: UDS-REQ-020
        [xray_test_key: UDS-220]
        """
        # Step 1: Request seed
        seed_response = uds.security_access_request_seed(access_level=0x01)
        assert seed_response.is_positive, "SecurityAccess seed request failed"
        assert len(seed_response.payload) >= 4, "Seed too short"

        seed = int.from_bytes(seed_response.payload[:4], byteorder="big")
        assert seed != 0, "ECU returned zero seed — unexpected"

        # Step 2: Calculate and send key
        key = UDSHelper.calculate_key(seed, security_level=0x01)
        key_response = uds.security_access_send_key(key, access_level=0x02)

        assert key_response.is_positive, (
            f"Security key rejected: NRC=0x{key_response.nrc:02X} "
            f"[{key_response.nrc_description}]"
        )

        report_generator.add_result(TestResultRow(
            test_id     = "UDS-TC-0x27-VALID",
            test_name   = "Security access — valid key",
            feature     = "UDS",
            status      = "PASS",
            duration_ms = 300,
            requirement = "UDS-REQ-020",
            xray_key    = "UDS-220",
        ))

    @pytest.mark.regression
    @pytest.mark.security
    def test_security_access_invalid_key_rejected(self, uds, report_generator):
        """
        ECU must reject an incorrect key with NRC 0x35 (invalidKey).

        Requirement: UDS-REQ-021
        [xray_test_key: UDS-221]
        """
        # Request seed
        seed_response = uds.security_access_request_seed(access_level=0x01)
        assert seed_response.is_positive

        # Send deliberately wrong key
        wrong_key = 0xDEADBEEF
        key_response = uds.security_access_send_key(wrong_key, access_level=0x02)

        assert not key_response.is_positive, "ECU accepted wrong key — security failure!"
        assert key_response.nrc == 0x35, (
            f"Expected NRC 0x35 (invalidKey), got 0x{key_response.nrc:02X} "
            f"[{key_response.nrc_description}]"
        )

        report_generator.add_result(TestResultRow(
            test_id     = "UDS-TC-0x27-INVALID",
            test_name   = "Security access — invalid key rejection",
            feature     = "UDS",
            status      = "PASS",
            duration_ms = 300,
            requirement = "UDS-REQ-021",
            xray_key    = "UDS-221",
        ))


# ══════════════════════════════════════════════════════════════════════
# DTC Read & Clear (0x19 + 0x14)
# ══════════════════════════════════════════════════════════════════════

class TestUDSDTC:
    """UDS DTC read, verify, and clear workflow."""

    @pytest.mark.regression
    @pytest.mark.dtc
    @pytest.mark.usefixtures("clear_dtcs")
    def test_read_dtc_after_seeding(self, uds, canoe, report_generator):
        """
        After seeding a known fault, ReadDTCInformation must report it as confirmed.

        Requirement: UDS-REQ-030
        [xray_test_key: UDS-230]
        """
        # Seed a fault via fault injection system variable
        KNOWN_DTC_CODE = 0x9A1201

        canoe.set_system_variable("FaultInjection", "Seed_DTC_9A1201", 1)
        time.sleep(1.5)  # Wait for DTC to be confirmed by ECU

        # Read DTCs
        dtcs = uds.read_dtc_by_status_mask(status_mask=0x08)  # confirmed DTC mask

        codes = [dtc.code for dtc in dtcs]
        assert KNOWN_DTC_CODE in codes, (
            f"DTC 0x{KNOWN_DTC_CODE:06X} not found in ECU response. "
            f"Found: {[hex(c) for c in codes]}"
        )

        # Verify confirmed bit is set
        matching_dtc = next(d for d in dtcs if d.code == KNOWN_DTC_CODE)
        assert matching_dtc.is_confirmed, (
            f"DTC 0x{KNOWN_DTC_CODE:06X} found but confirmed bit (bit 3) not set"
        )

        report_generator.add_result(TestResultRow(
            test_id     = "UDS-TC-0x19-SEED",
            test_name   = "ReadDTC after fault seeding",
            feature     = "UDS",
            status      = "PASS",
            duration_ms = 1500,
            requirement = "UDS-REQ-030",
            xray_key    = "UDS-230",
            dtc_present = True,
            notes       = f"DTC 0x{KNOWN_DTC_CODE:06X} confirmed",
        ))

    @pytest.mark.regression
    @pytest.mark.dtc
    def test_clear_dtc_clears_all(self, uds, report_generator):
        """
        After ClearDTC, ReadDTCInformation must return an empty DTC list.

        Requirement: UDS-REQ-031
        [xray_test_key: UDS-231]
        """
        clear_response = uds.clear_dtc(group_of_dtc=0xFFFFFF)
        assert clear_response.is_positive, (
            f"ClearDTC failed: NRC=0x{clear_response.nrc:02X}"
        )

        time.sleep(0.5)

        dtcs = uds.read_dtc_by_status_mask(status_mask=0x08)
        assert len(dtcs) == 0, (
            f"DTCs still present after ClearDTC: {[d.code_hex for d in dtcs]}"
        )

        report_generator.add_result(TestResultRow(
            test_id     = "UDS-TC-0x14-CLEAR",
            test_name   = "ClearDTC — verify empty DTC list",
            feature     = "UDS",
            status      = "PASS",
            duration_ms = 600,
            requirement = "UDS-REQ-031",
            xray_key    = "UDS-231",
            dtc_present = False,
        ))


# ══════════════════════════════════════════════════════════════════════
# ECU Reset (0x11)
# ══════════════════════════════════════════════════════════════════════

class TestUDSECUReset:
    """UDS 0x11 ECUReset — verify ECU re-initialises correctly."""

    @pytest.mark.regression
    @pytest.mark.parametrize("reset_type,name,timeout_ms", [
        (0x01, "Hard reset",       3000),
        (0x03, "Soft reset",       1500),
    ])
    def test_ecu_reset(self, reset_type, name, timeout_ms, uds, canoe, report_generator):
        """
        ECU must respond positively to reset and re-initialise within timeout.

        Requirement: UDS-REQ-040
        [xray_test_key: UDS-240]
        """
        response = uds.ecu_reset(reset_type)
        assert response.is_positive, (
            f"ECUReset 0x{reset_type:02X} ({name}) rejected: "
            f"NRC={response.nrc_description}"
        )

        # Wait for ECU to boot back up
        time.sleep(timeout_ms / 1000.0)

        # Verify ECU is alive by checking default session
        session_resp = uds.session_control(0x01)
        assert session_resp.is_positive, (
            f"ECU did not return to default session after {name}"
        )

        report_generator.add_result(TestResultRow(
            test_id     = f"UDS-TC-0x11-{reset_type:02X}",
            test_name   = f"ECU Reset — {name}",
            feature     = "UDS",
            status      = "PASS",
            duration_ms = timeout_ms,
            requirement = "UDS-REQ-040",
            xray_key    = "UDS-240",
        ))
