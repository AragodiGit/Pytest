import pytest 

@pytest.fixture(scope="session")
def web():
    print("Login successful")
    print("Browse cart...")
    yield
    print("Logout successful")

def is_ecu_alive():
    return True

@pytest.fixture(autouse=True)
def hil_setup():
    print("Rig initialization")

    if not is_ecu_alive():
        pytest.skip("ECU is not alive, skipping test")

    print("CANalyzer start logging")
    print("Vehicle is single locked")
    print("Door handles are retracted")
    yield
    print("Capture MDF log")
    print("CANalyzer stop logging")
    print("HIL cleanup")
