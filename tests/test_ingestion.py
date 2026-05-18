from patchly_rca.ingestion import ingest, Incident, IngestionError


def test_ingest_text_message():
    cfg = {"default_source": "auto", "text_message": {"id_prefix": "TXT", "counter_file": "/tmp/test_counter.txt"}}
    incident = ingest("payment service is down", cfg)
    assert incident.source == "text_message"
    assert "payment" in incident.summary


def test_ingest_json_payload():
    cfg = {"default_source": "auto", "text_message": {"id_prefix": "INC", "counter_file": "/tmp/test_counter2.txt"}}
    incident = ingest('{"text": "API 503", "service": "checkout"}', cfg)
    assert incident.source == "json_payload"
    assert incident.summary == "API 503"


def test_ingest_missing_log_file():
    cfg = {"default_source": "log_file"}
    try:
        ingest("/nonexistent/path/app.log", cfg)
        assert False, "Should have raised IngestionError"
    except IngestionError:
        pass
