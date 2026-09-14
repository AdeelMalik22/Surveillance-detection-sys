from app.detector import Detector, SUPPORTED_CLASSES


def test_supported_classes_are_person_and_vehicles():
    assert SUPPORTED_CLASSES == {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def test_invalid_confidence_is_rejected_without_loading_model():
    try:
        Detector(confidence=1.1)
    except ValueError as error:
        assert "confidence" in str(error)
    else:
        raise AssertionError("invalid confidence was accepted")
