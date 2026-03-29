# ============================================================
# Feature: BCM Door Lock Control via CAN
# ECU: Body Control Module (BCM)
# Protocol: CAN FD  |  Bench: dSPACE HIL
# Author: Rakesh Aragodi
# ============================================================

@bcm @regression
Feature: BCM door lock control via CAN signal

  Background:
    Given the BCM ECU is powered on and in default diagnostic session
    And the HIL bench is connected and measurement is running
    And the vehicle speed signal "VehicleSpeed_kph" is set to 0

  # ----------------------------------------------------------
  # Scenario 1: Basic lock command
  # ----------------------------------------------------------
  @smoke
  Scenario: BCM locks all doors on valid CAN lock command
    When a CAN frame is sent on bus "Comfort" with ID 0x321 and data 0x01
    Then the BCM output signal "DoorLock_Status_FL" should equal 1 within 500 ms
    And  the BCM output signal "DoorLock_Status_FR" should equal 1 within 500 ms
    And  the BCM output signal "DoorLock_Status_RL" should equal 1 within 500 ms
    And  the BCM output signal "DoorLock_Status_RR" should equal 1 within 500 ms
    And  no DTC should be present in the BCM ECU

  # ----------------------------------------------------------
  # Scenario 2: Unlock command
  # ----------------------------------------------------------
  @smoke
  Scenario: BCM unlocks all doors on valid CAN unlock command
    Given all doors are currently locked
    When a CAN frame is sent on bus "Comfort" with ID 0x321 and data 0x00
    Then the BCM output signal "DoorLock_Status_FL" should equal 0 within 500 ms
    And  the BCM output signal "DoorLock_Status_FR" should equal 0 within 500 ms
    And  no DTC should be present in the BCM ECU

  # ----------------------------------------------------------
  # Scenario 3: Lock inhibited above speed threshold
  # ----------------------------------------------------------
  @regression @safety
  Scenario: BCM ignores lock command when vehicle speed exceeds threshold
    Given the vehicle speed signal "VehicleSpeed_kph" is set to 120
    When a CAN frame is sent on bus "Comfort" with ID 0x321 and data 0x01
    Then the BCM output signal "DoorLock_Status_FL" should equal 0 within 500 ms
    And  the DTC "0x9A1201" should be present in the BCM ECU

  # ----------------------------------------------------------
  # Scenario 4: Data-driven — multiple CAN IDs and payloads
  # ----------------------------------------------------------
  @regression @data_driven
  Scenario Outline: BCM responds correctly to various door lock command payloads
    When a CAN frame is sent on bus "Comfort" with ID <can_id> and data <payload>
    Then the BCM output signal "DoorLock_Status_FL" should equal <expected_status> within 500 ms
    And  no DTC should be present in the BCM ECU

    Examples: Door lock command matrix
      | can_id | payload | expected_status | description          |
      | 0x321  | 0x01    | 1               | Standard lock        |
      | 0x321  | 0x00    | 0               | Standard unlock      |
      | 0x321  | 0x0F    | 1               | Lock all doors       |
      | 0x321  | 0xF0    | 0               | Unlock all doors     |

  # ----------------------------------------------------------
  # Scenario 5: Fault injection — CAN bus-off recovery
  # ----------------------------------------------------------
  @regression @fault_injection
  Scenario: BCM recovers gracefully after CAN bus-off condition
    Given a CAN bus-off fault is injected on bus "Comfort"
    When the CAN bus-off fault is cleared after 2000 ms
    Then the BCM ECU should re-initialise the CAN node within 3000 ms
    And  the BCM output signal "CAN_BusOff_Flag" should equal 0 within 5000 ms
    And  the DTC "0x9A0001" should be present in the BCM ECU
