import numpy as np

from actions import RetryPolicy, perform_verified
from utilities.red_click import RedClickVerifier, has_red_click_marker


def test_perform_verified_retries_until_the_predicate_observes_the_outcome():
    attempts = []

    result = perform_verified(
        lambda: attempts.append("click"),
        verify=lambda: len(attempts) == 2,
        retry_policy=RetryPolicy(max_attempts=3),
    )

    assert result.succeeded
    assert result.attempts == 2
    assert result.reason == "verified"


def test_perform_verified_stops_when_verification_raises():
    result = perform_verified(lambda: None, verify=lambda: (_ for _ in ()).throw(RuntimeError("capture lost")))

    assert not result.succeeded
    assert result.attempts == 1
    assert result.reason == "verification_error"
    assert isinstance(result.error, RuntimeError)


def test_red_click_marker_detection_is_local_and_bounds_checked():
    image = np.zeros((30, 30, 3), dtype=np.uint8)
    image[14:16, 14:16] = (10, 20, 220)  # BGR

    assert has_red_click_marker(image, (114, 214), (100, 200))
    assert not has_red_click_marker(image, (200, 300), (100, 200))
    assert not has_red_click_marker(image, (114, 214), (100, 200), minimum_pixels=5)


def test_red_click_verifier_fails_closed_when_capture_fails():
    verifier = RedClickVerifier(lambda: (_ for _ in ()).throw(OSError("capture unavailable")), (0, 0))

    assert verifier((10, 10)) is False
