"""
uds_helper.py
=============
UDS (ISO 14229-1) service request builder and response parser.

Provides clean, reusable helpers for building UDS requests and
interpreting ECU responses — used by both BDD steps and pytest tests.

Author : Rakesh Aragodi
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── UDS Service IDs ────────────────────────────────────────────────────
SERVICE = {
    "DiagnosticSessionControl"  : 0x10,
    "ECUReset"                  : 0x11,
    "ClearDTC"                  : 0x14,
    "ReadDTCInformation"        : 0x19,
    "ReadDataByIdentifier"      : 0x22,
    "WriteDataByIdentifier"     : 0x2E,
    "SecurityAccess"            : 0x27,
    "RequestDownload"           : 0x34,
    "TransferData"              : 0x36,
    "RequestTransferExit"       : 0x37,
}

POSITIVE_RESPONSE_OFFSET = 0x40   # positive SID = request SID + 0x40
NEGATIVE_RESPONSE_SID    = 0x7F

# ── Negative Response Codes ────────────────────────────────────────────
NRC = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat",
    0x22: "conditionsNotCorrect",
    0x24: "requestSequenceError",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x36: "exceededNumberOfAttempts",
    0x37: "requiredTimeDelayNotExpired",
    0x70: "uploadDownloadNotAccepted",
    0x71: "transferDataSuspended",
    0x72: "generalProgrammingFailure",
    0x73: "wrongBlockSequenceCounter",
    0x78: "requestCorrectlyReceivedResponsePending",
    0x7E: "subFunctionNotSupportedInActiveSession",
    0x7F: "serviceNotSupportedInActiveSession",
}

# ── DTC Status bit definitions (ISO 14229-1 Table D.5) ────────────────
DTC_STATUS_BITS = {
    0: "testFailed",
    1: "testFailedThisOperationCycle",
    2: "pendingDTC",
    3: "confirmedDTC",
    4: "testNotCompletedSinceLastClear",
    5: "testFailedSinceLastClear",
    6: "testNotCompletedThisOperationCycle",
    7: "warningIndicatorRequested",
}


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass
class UDSResponse:
    """Parsed UDS ECU response."""
    raw:           bytes
    service_id:    int
    is_positive:   bool
    sub_function:  Optional[int]     = None
    payload:       bytes             = field(default_factory=bytes)
    nrc:           Optional[int]     = None
    nrc_description: Optional[str]  = None

    @property
    def positive_sid(self) -> int:
        return self.service_id + POSITIVE_RESPONSE_OFFSET

    def __repr__(self) -> str:
        if self.is_positive:
            return (
                f"UDSResponse(SID=0x{self.service_id:02X}, "
                f"POSITIVE, payload={self.payload.hex()})"
            )
        return (
            f"UDSResponse(SID=0x{self.service_id:02X}, "
            f"NEGATIVE, NRC=0x{self.nrc:02X} [{self.nrc_description}])"
        )


@dataclass
class DTCRecord:
    """A single DTC from a ReadDTCInformation response."""
    code:        int
    status_byte: int

    @property
    def code_hex(self) -> str:
        return f"0x{self.code:06X}"

    @property
    def active_status_bits(self) -> list[str]:
        return [
            DTC_STATUS_BITS[bit]
            for bit in range(8)
            if self.status_byte & (1 << bit)
        ]

    @property
    def is_confirmed(self) -> bool:
        return bool(self.status_byte & 0x08)   # bit 3

    def __repr__(self) -> str:
        return f"DTCRecord(code={self.code_hex}, status=0x{self.status_byte:02X})"


# ──────────────────────────────────────────────────────────────────────
# UDS response parser
# ──────────────────────────────────────────────────────────────────────

class UDSResponseParser:
    """Parse raw bytes from an ECU UDS response into a UDSResponse object."""

    @staticmethod
    def parse(raw_bytes: bytes, request_sid: int) -> UDSResponse:
        """
        Parse a raw ECU response.

        Args:
            raw_bytes:   Raw response bytes from ECU
            request_sid: The SID of the request that triggered this response

        Returns:
            UDSResponse dataclass
        """
        if not raw_bytes:
            raise ValueError("Empty response — ECU did not respond")

        response_sid = raw_bytes[0]

        # Negative response
        if response_sid == NEGATIVE_RESPONSE_SID:
            nrc_code = raw_bytes[2] if len(raw_bytes) >= 3 else None
            return UDSResponse(
                raw=raw_bytes,
                service_id=request_sid,
                is_positive=False,
                nrc=nrc_code,
                nrc_description=NRC.get(nrc_code, "unknown"),
            )

        # Positive response
        positive_sid = request_sid + POSITIVE_RESPONSE_OFFSET
        if response_sid != positive_sid:
            raise ValueError(
                f"Unexpected response SID 0x{response_sid:02X} "
                f"(expected 0x{positive_sid:02X})"
            )

        sub_fn  = raw_bytes[1] if len(raw_bytes) > 1 else None
        payload = raw_bytes[2:] if len(raw_bytes) > 2 else b""

        return UDSResponse(
            raw=raw_bytes,
            service_id=request_sid,
            is_positive=True,
            sub_function=sub_fn,
            payload=payload,
        )

    @staticmethod
    def parse_dtc_list(payload: bytes) -> list[DTCRecord]:
        """
        Parse DTC records from a ReadDTCInformation (0x19) positive response payload.

        Each DTC record is 4 bytes: 3-byte DTC code + 1-byte status mask.
        """
        dtcs = []
        i = 0
        while i + 3 < len(payload):
            code = (payload[i] << 16) | (payload[i + 1] << 8) | payload[i + 2]
            status = payload[i + 3]
            dtcs.append(DTCRecord(code=code, status_byte=status))
            i += 4

        logger.info("Parsed %d DTC records from payload", len(dtcs))
        return dtcs


# ──────────────────────────────────────────────────────────────────────
# UDS request builder helpers
# ──────────────────────────────────────────────────────────────────────

class UDSHelper:
    """
    High-level UDS helper — wraps CANoeInterface.send_uds_request()
    with named service helpers and automatic response parsing.
    """

    def __init__(self, canoe):
        self._canoe = canoe

    def session_control(self, session_type: int) -> UDSResponse:
        """0x10 DiagnosticSessionControl."""
        raw = self._canoe.send_uds_request(
            service_id=SERVICE["DiagnosticSessionControl"],
            sub_function=session_type,
        )
        return UDSResponseParser.parse(raw, SERVICE["DiagnosticSessionControl"])

    def ecu_reset(self, reset_type: int) -> UDSResponse:
        """0x11 ECUReset — 0x01=hard, 0x02=key off/on, 0x03=soft."""
        raw = self._canoe.send_uds_request(
            service_id=SERVICE["ECUReset"],
            sub_function=reset_type,
        )
        return UDSResponseParser.parse(raw, SERVICE["ECUReset"])

    def read_data_by_identifier(self, did: int) -> UDSResponse:
        """0x22 ReadDataByIdentifier — read a single DID."""
        did_high = (did >> 8) & 0xFF
        did_low  = did & 0xFF
        raw = self._canoe.send_uds_request(
            service_id=SERVICE["ReadDataByIdentifier"],
            data=bytes([did_high, did_low]),
        )
        return UDSResponseParser.parse(raw, SERVICE["ReadDataByIdentifier"])

    def security_access_request_seed(self, access_level: int = 0x01) -> UDSResponse:
        """0x27 SecurityAccess — step 1: request seed."""
        raw = self._canoe.send_uds_request(
            service_id=SERVICE["SecurityAccess"],
            sub_function=access_level,
        )
        return UDSResponseParser.parse(raw, SERVICE["SecurityAccess"])

    def security_access_send_key(self, key: int, access_level: int = 0x02) -> UDSResponse:
        """0x27 SecurityAccess — step 2: send calculated key."""
        key_bytes = key.to_bytes(4, byteorder="big")
        raw = self._canoe.send_uds_request(
            service_id=SERVICE["SecurityAccess"],
            sub_function=access_level,
            data=key_bytes,
        )
        return UDSResponseParser.parse(raw, SERVICE["SecurityAccess"])

    def read_dtc_by_status_mask(self, status_mask: int = 0x08) -> list[DTCRecord]:
        """0x19 ReadDTCInformation — sub-function 0x02 reportDTCByStatusMask."""
        raw = self._canoe.send_uds_request(
            service_id=SERVICE["ReadDTCInformation"],
            sub_function=0x02,
            data=bytes([status_mask]),
        )
        response = UDSResponseParser.parse(raw, SERVICE["ReadDTCInformation"])
        if not response.is_positive:
            return []
        return UDSResponseParser.parse_dtc_list(response.payload)

    def clear_dtc(self, group_of_dtc: int = 0xFFFFFF) -> UDSResponse:
        """0x14 ClearDiagnosticInformation."""
        data = group_of_dtc.to_bytes(3, byteorder="big")
        raw = self._canoe.send_uds_request(
            service_id=SERVICE["ClearDTC"],
            data=data,
        )
        return UDSResponseParser.parse(raw, SERVICE["ClearDTC"])

    @staticmethod
    def calculate_key(seed: int, security_level: int = 0x01) -> int:
        """
        Example seed-key algorithm (project-specific — replace with actual).
        This is a placeholder XOR-based algorithm for demonstration.
        """
        mask = {0x01: 0xA5A5A5A5, 0x03: 0x5A5A5A5A}.get(security_level, 0xFFFFFFFF)
        return (seed ^ mask) & 0xFFFFFFFF
