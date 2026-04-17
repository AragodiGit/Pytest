"""
canoe_interface.py
==================
Vector CANoe COM automation interface wrapper.

Wraps win32com.client calls into a clean, testable Python API
used by both BDD steps and pytest test cases.

Author : Rakesh Aragodi
Project: Automotive ECU Test Automation Framework
"""

import time
import logging
from typing import Any, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class CANoeConnectionError(Exception):
    """Raised when CANoe application cannot be reached."""


class SignalTimeoutError(Exception):
    """Raised when a signal does not reach expected value within timeout."""


class CANoeInterface:
    """
    Thin Python wrapper around the Vector CANoe COM automation API.

    Usage (in pytest fixture):
        canoe = CANoeInterface()
        canoe.open(r"C:\\HIL\\configs\\BCM_SDV.cfg")
        canoe.start_measurement()
        yield canoe
        canoe.stop_measurement()
    """

    def __init__(self):
        self._app = None
        self._measurement_running = False

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def open(self, config_path: str) -> None:
        """Open a CANoe configuration file."""
        try:
            import win32com.client  # pywin32 — only available on Windows HIL bench
            self._app = win32com.client.Dispatch("CANoe.Application")
            self._app.Open(config_path, False, False)
            logger.info("CANoe config opened: %s", config_path)
        except ImportError:
            # Running on CI without hardware — use mock
            logger.warning("win32com not available — using MockCANoeApp")
            self._app = _MockCANoeApp()
        except Exception as exc:
            raise CANoeConnectionError(
                f"Failed to open CANoe config '{config_path}': {exc}"
            ) from exc

    def start_measurement(self, stabilise_seconds: float = 2.0) -> None:
        """Start CANoe measurement and wait for the bus to stabilise."""
        self._app.Measurement.Start()
        time.sleep(stabilise_seconds)
        self._measurement_running = True
        logger.info("CANoe measurement started (waited %.1fs)", stabilise_seconds)

    def stop_measurement(self) -> None:
        """Stop CANoe measurement."""
        if self._measurement_running:
            self._app.Measurement.Stop()
            self._measurement_running = False
            logger.info("CANoe measurement stopped")

    def quit(self) -> None:
        """Close CANoe application."""
        self.stop_measurement()
        self._app.Quit()
        logger.info("CANoe application closed")

    # ------------------------------------------------------------------
    # Signal read / write
    # ------------------------------------------------------------------

    def get_signal_value(
        self, network: str, message: str, signal: str
    ) -> Any:
        """
        Read current value of a CAN signal.

        Args:
            network: CANoe network name  e.g. "Comfort"
            message: Message name        e.g. "DoorControl"
            signal:  Signal name         e.g. "DoorLock_Status_FL"

        Returns:
            Current signal value (int or float).
        """
        try:
            bus = self._app.Networks.Item(network)
            msg = bus.Messages.Item(message)
            sig = msg.Signals.Item(signal)
            value = sig.Value
            logger.debug("GET  %s::%s::%s = %s", network, message, signal, value)
            return value
        except Exception as exc:
            logger.error("Failed to read signal %s::%s::%s — %s", network, message, signal, exc)
            raise

    def set_signal_value(
        self, network: str, message: str, signal: str, value: Any
    ) -> None:
        """Write a value to a CAN signal (stimulation)."""
        try:
            bus = self._app.Networks.Item(network)
            msg = bus.Messages.Item(message)
            sig = msg.Signals.Item(signal)
            sig.Value = value
            logger.debug("SET  %s::%s::%s = %s", network, message, signal, value)
        except Exception as exc:
            logger.error("Failed to write signal %s::%s::%s — %s", network, message, signal, exc)
            raise

    # ------------------------------------------------------------------
    # Polling helper — never use bare time.sleep() in test assertions
    # ------------------------------------------------------------------

    def wait_for_signal(
        self,
        network: str,
        message: str,
        signal: str,
        expected_value: Any,
        timeout_ms: int = 1000,
        poll_interval_ms: int = 50,
    ) -> bool:
        """
        Poll a signal until it reaches expected_value or timeout expires.

        Args:
            timeout_ms:       Maximum wait time in milliseconds.
            poll_interval_ms: How often to re-read the signal.

        Returns:
            True if signal reached expected value within timeout.

        Raises:
            SignalTimeoutError if the signal did not reach expected value.
        """
        deadline = time.monotonic() + timeout_ms / 1000.0
        last_value = None

        while time.monotonic() < deadline:
            last_value = self.get_signal_value(network, message, signal)
            if last_value == expected_value:
                logger.info(
                    "Signal %s reached %s in < %d ms", signal, expected_value, timeout_ms
                )
                return True
            time.sleep(poll_interval_ms / 1000.0)

        raise SignalTimeoutError(
            f"Signal '{signal}' did not reach {expected_value} within {timeout_ms} ms. "
            f"Last observed value: {last_value}"
        )

    # ------------------------------------------------------------------
    # CAN frame transmission
    # ------------------------------------------------------------------

    def send_can_frame(
        self, network: str, can_id: int, data: bytes, channel: int = 1
    ) -> None:
        """
        Transmit a raw CAN frame.

        Args:
            network:  CANoe network name e.g. "Comfort"
            can_id:   11-bit or 29-bit CAN identifier
            data:     Payload bytes (max 8 bytes for classic CAN, 64 for CAN FD)
            channel:  CAN channel number (default 1)
        """
        try:
            output = self._app.Networks.Item(network).OutputPort
            output.Send(can_id, channel, 0, len(data), data)
            logger.info("CAN TX  ID=0x%03X  data=%s  ch=%d", can_id, data.hex(), channel)
        except Exception as exc:
            logger.error("Failed to send CAN frame — %s", exc)
            raise

    # ------------------------------------------------------------------
    # Environment variable access (CANoe system variables)
    # ------------------------------------------------------------------

    def get_system_variable(self, namespace: str, variable: str) -> Any:
        """Read a CANoe system variable (::namespace::variable)."""
        sysvar = self._app.System.Namespaces.Item(namespace).Variables.Item(variable)
        return sysvar.Value

    def set_system_variable(self, namespace: str, variable: str, value: Any) -> None:
        """Write a CANoe system variable."""
        sysvar = self._app.System.Namespaces.Item(namespace).Variables.Item(variable)
        sysvar.Value = value
        logger.debug("SYSVAR %s::%s = %s", namespace, variable, value)

    # ------------------------------------------------------------------
    # Diagnostic (UDS) interface
    # ------------------------------------------------------------------

    def send_uds_request(
        self, service_id: int, sub_function: Optional[int] = None, data: bytes = b""
    ) -> bytes:
        """
        Send a UDS diagnostic request and return the raw response bytes.

        Args:
            service_id:   UDS service identifier (e.g. 0x22)
            sub_function: Optional sub-function byte  (e.g. 0x01 for SecurityAccess)
            data:         Additional payload bytes

        Returns:
            Response payload as bytes (excludes the response SID byte).
        """
        diag = self._app.Networks.Item("Diagnostics").DiagnosticClient
        request = diag.CreateRequest(service_id)

        if sub_function is not None:
            request.SubFunction = sub_function

        if data:
            for i, byte_val in enumerate(data):
                request.SetParameter(i, byte_val)

        response = request.Send()
        raw = bytes([response.GetResponseByte(i) for i in range(response.ResponseLength)])
        logger.info(
            "UDS  SID=0x%02X  subfn=%s  response=%s",
            service_id,
            hex(sub_function) if sub_function else "N/A",
            raw.hex(),
        )
        return raw

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    @contextmanager
    def measurement_session(self, config_path: str, stabilise_seconds: float = 2.0):
        """Context manager: open config, start measurement, yield, stop."""
        self.open(config_path)
        self.start_measurement(stabilise_seconds)
        try:
            yield self
        finally:
            self.stop_measurement()


# ======================================================================
# Mock — used in CI (no CANoe hardware available)
# ======================================================================

class _MockCANoeApp:
    """
    Minimal CANoe mock for running tests in CI without hardware.
    Returns sensible defaults so the framework can be validated structurally.
    """

    class _MockMeasurement:
        def Start(self): logger.debug("[MOCK] Measurement started")
        def Stop(self):  logger.debug("[MOCK] Measurement stopped")

    class _MockSignal:
        def __init__(self): self.Value = 0

    class _MockMessage:
        def Signals(self): return {"_": _MockCANoeApp._MockSignal()}
        def Item(self, _): return _MockCANoeApp._MockSignal()

    class _MockBus:
        def Messages(self): return {}
        def Item(self, _): return _MockCANoeApp._MockMessage()

    class _MockNetworks:
        def Item(self, _): return _MockCANoeApp._MockBus()

    Measurement = _MockMeasurement()
    Networks    = _MockNetworks()

    def Open(self, *args): logger.debug("[MOCK] CANoe.Open(%s)", args[0])
    def Quit(self):        logger.debug("[MOCK] CANoe.Quit()")
