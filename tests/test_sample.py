import pytest


def add(x):
    print("Adding 1 to", x)
    return x + 1

def login(username, password):
    print("Logging in user:", username)
    return username == "test_user" and password == "test_pass"

@pytest.mark.parametrize("input,expected", [(1, 2), (2, 3), (3, 4), (4, 5)])
def test_add(input, expected):
    assert add(input) == expected


@pytest.mark.parametrize("user, passw", [("test_user", "test_pass"), ("test_user", "wrong_pass"), ("wrong_user", "test_pass"), ("wrong_user", "wrong_pass")])
def test_login_success(user, passw):
    assert login(user, passw) == (user == "test_user" and passw == "test_pass")
