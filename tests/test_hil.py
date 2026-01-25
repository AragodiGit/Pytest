import pytest
import logging

logging.basicConfig(level=logging.INFO)

@pytest.mark.hil
@pytest.mark.parametrize("door_ajar, interior_unlock_button_status, expected", [("driver", "not pressed", False), ("passenger", "pressed", True)])
def test_door_handle_deployment_on_interior_unlock(door_ajar, interior_unlock_button_status, expected):
    door_handle_deploy = interior_unlock_button_status == "pressed"

    assert door_handle_deploy==expected, f"{door_ajar} door handle did not deploy on interior unlock or unlock button not pressed"

@pytest.mark.flaky(reruns=3)
def test_flaky():
    import random
    value = random.choice([True, False])
    logging.info("This is a flaky test that may fail intermittently.")
    assert value, "Flaky test failed this time."