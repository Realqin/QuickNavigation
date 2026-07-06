from app.k8s_alarm_evaluator_service import detect_restart_increase


def test_baseline_skips_historical_restart_counts():
    increased, keys = detect_restart_increase(
        None,
        {"pod-a/app": 12, "pod-a/sidecar": 3},
        is_baseline=True,
    )
    assert increased is False
    assert keys == []


def test_detect_increase_on_same_pod_container():
    previous = {"pod-a/app": 2, "pod-a/sidecar": 0}
    current = {"pod-a/app": 3, "pod-a/sidecar": 0}
    increased, keys = detect_restart_increase(previous, current, is_baseline=False)
    assert increased is True
    assert keys == ["pod-a/app"]


def test_ignore_pod_rollout_without_restart_on_new_pod():
    previous = {"pod-old/app": 5}
    current = {"pod-new/app": 0}
    increased, keys = detect_restart_increase(previous, current, is_baseline=False)
    assert increased is False
    assert keys == []


def test_detect_new_pod_that_already_restarted():
    previous = {"pod-a/app": 0}
    current = {"pod-a/app": 0, "pod-b/app": 2}
    increased, keys = detect_restart_increase(previous, current, is_baseline=False)
    assert increased is True
    assert keys == ["pod-b/app"]


def test_ignore_scale_up_with_zero_restarts():
    previous = {"pod-a/app": 1}
    current = {"pod-a/app": 1, "pod-b/app": 0}
    increased, keys = detect_restart_increase(previous, current, is_baseline=False)
    assert increased is False
    assert keys == []
