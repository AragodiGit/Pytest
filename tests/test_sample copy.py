def add(x):
    print("Adding 1 to", x)
    return x + 1

def test():
    print("Testing positive numbers:")
    assert add(1) == 2
    assert add(2) == 3
    assert add(3) == 4
    assert add(4) == 5

def test_negative():
    print("Testing negative numbers:")
    assert add(-1) == 0
    assert add(-2) == -1
    assert add(-3) == -2
    assert add(-4) == -3
