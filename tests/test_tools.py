from patchly_rca.tools.analysis_tools import analyze_metrics


def test_analyze_metrics_anomaly():
    result = analyze_metrics('{"cpu_pct": 95, "memory_pct": 90}')
    assert "ANOMALIES" in result
    assert "cpu_pct" in result


def test_analyze_metrics_normal():
    result = analyze_metrics('{"cpu_pct": 10, "memory_pct": 20}')
    assert "No anomalies detected" in result


def test_analyze_metrics_invalid_json():
    result = analyze_metrics("not-json")
    assert "Invalid JSON" in result
