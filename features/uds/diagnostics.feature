# ============================================================
# Feature: UDS Diagnostic Services Validation
# ECU: BCM / Infotainment ECU
# Standard: ISO 14229-1 (UDS)
# Author: Rakesh Aragodi
# ============================================================

@uds @regression
Feature: UDS diagnostic service validation

  Background:
    Given the ECU is connected via CANoe diagnostic channel
    And the ECU is in the default diagnostic session (0x01)

  # ----------------------------------------------------------
  # Scenario 1: Session switching
  # ----------------------------------------------------------
  @smoke
  Scenario Outline: ECU switches to requested diagnostic session
    When UDS service 0x10 is sent with sub-function <session_type>
    Then the positive response SID should be 0x50
    And  the response sub-function should be <session_type>

    Examples: Diagnostic sessions
      | session_type | description              |
      | 0x01         | Default session          |
      | 0x02         | Programming session      |
      | 0x03         | Extended diagnostic session |

  # ----------------------------------------------------------
  # Scenario 2: Read DID - software version
  # ----------------------------------------------------------
  @smoke
  Scenario: ECU returns software version via ReadDataByIdentifier
    When UDS service 0x22 is sent with DID 0xF189
    Then the positive response SID should be 0x62
    And  the response data length should be greater than 0
    And  the response should contain a valid ASCII software version string

  # ----------------------------------------------------------
  # Scenario 3: Security access - seed/key exchange
  # ----------------------------------------------------------
  @regression @security
  Scenario: ECU grants security access via valid seed-key exchange
    Given the ECU is in extended diagnostic session (0x03)
    When UDS service 0x27 is sent with sub-function 0x01 to request seed
    Then the positive response SID should be 0x67
    And  the seed value in response should be non-zero
    When the calculated key is sent using UDS service 0x27 sub-function 0x02
    Then the positive response SID should be 0x67
    And  the ECU should be in unlocked security state

  # ----------------------------------------------------------
  # Scenario 4: Security access - invalid key rejection
  # ----------------------------------------------------------
  @regression @security
  Scenario: ECU rejects invalid security key and sets attempt counter
    Given the ECU is in extended diagnostic session (0x03)
    When UDS service 0x27 is sent with sub-function 0x01 to request seed
    And  an incorrect key 0xDEADBEEF is sent using UDS service 0x27 sub-function 0x02
    Then a negative response 0x7F should be received
    And  the NRC (Negative Response Code) should be 0x35 (invalidKey)

  # ----------------------------------------------------------
  # Scenario 5: Read DTC information
  # ----------------------------------------------------------
  @regression @dtc
  Scenario: ECU reports confirmed DTCs via ReadDTCInformation
    Given a known DTC "0x9A1201" has been seeded into the ECU
    When UDS service 0x19 is sent with sub-function 0x02 and mask 0x08
    Then the positive response SID should be 0x59
    And  the DTC "0x9A1201" should appear in the response
    And  the DTC status byte should have bit 3 set (confirmed DTC)

  # ----------------------------------------------------------
  # Scenario 6: Clear DTC
  # ----------------------------------------------------------
  @regression @dtc
  Scenario: ECU clears all DTCs on ClearDiagnosticInformation request
    Given at least one DTC is present in the ECU
    When UDS service 0x14 is sent with group-of-DTC 0xFFFFFF
    Then the positive response SID should be 0x54
    When UDS service 0x19 is sent with sub-function 0x02 and mask 0x08
    Then the DTC list in the response should be empty

  # ----------------------------------------------------------
  # Scenario 7: ECU reset
  # ----------------------------------------------------------
  @regression @reset
  Scenario Outline: ECU performs requested reset type correctly
    When UDS service 0x11 is sent with sub-function <reset_type>
    Then the positive response SID should be 0x51
    And  the ECU should re-initialise within <timeout_ms> ms
    And  the ECU should return to default diagnostic session after reset

    Examples: Reset types
      | reset_type | timeout_ms | description     |
      | 0x01       | 3000       | Hard reset      |
      | 0x02       | 2000       | Key off/on reset|
      | 0x03       | 1500       | Soft reset      |
