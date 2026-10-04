def test_package_importable():
    import devpulse

    assert devpulse.__version__ == "0.1.0"
