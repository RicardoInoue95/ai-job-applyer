from unittest.mock import MagicMock, patch

from collectors.greenhouse import GreenhouseCollector
from collectors.lever import LeverCollector

GREENHOUSE_RESPONSE = {
    "jobs": [
        {
            "id": 1,
            "title": "Data Engineer",
            "location": {"name": "Remote"},
            "content": "<p>Responsibilities...</p>",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
            "updated_at": "2024-01-15T10:00:00Z",
        }
    ]
}

LEVER_RESPONSE = [
    {
        "id": "abc-123",
        "text": "Analytics Engineer",
        "categories": {"location": "São Paulo", "commitment": "Full-time"},
        "descriptionPlain": "Join our data team...",
        "hostedUrl": "https://jobs.lever.co/acme/abc-123",
        "createdAt": 1705315200000,
    }
]


def test_greenhouse_collect_returns_jobs():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = GREENHOUSE_RESPONSE
    mock_resp.raise_for_status.return_value = None

    with patch("collectors.greenhouse.requests.get", return_value=mock_resp):
        collector = GreenhouseCollector()
        jobs = collector.collect("acme")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.titulo == "Data Engineer"
    assert job.plataforma == "greenhouse"
    assert job.empresa == "acme"
    assert job.localizacao == "Remote"
    assert job.hash  # deve ter hash calculado


def test_greenhouse_collect_deduplicates_via_hash():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = GREENHOUSE_RESPONSE
    mock_resp.raise_for_status.return_value = None

    with patch("collectors.greenhouse.requests.get", return_value=mock_resp):
        collector = GreenhouseCollector()
        jobs1 = collector.collect("acme")
        jobs2 = collector.collect("acme")

    assert jobs1[0].hash == jobs2[0].hash


def test_greenhouse_collect_returns_empty_on_404():
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("collectors.greenhouse.requests.get", return_value=mock_resp):
        collector = GreenhouseCollector()
        jobs = collector.collect("nonexistent-company")

    assert jobs == []


def test_lever_collect_returns_jobs():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = LEVER_RESPONSE
    mock_resp.raise_for_status.return_value = None

    with patch("collectors.lever.requests.get", return_value=mock_resp):
        collector = LeverCollector()
        jobs = collector.collect("acme")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.titulo == "Analytics Engineer"
    assert job.plataforma == "lever"
    assert job.localizacao == "São Paulo"
    assert job.modalidade == "Full-time"


def test_lever_collect_returns_empty_on_404():
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("collectors.lever.requests.get", return_value=mock_resp):
        collector = LeverCollector()
        jobs = collector.collect("nonexistent")

    assert jobs == []


def test_collect_all_skips_failed_companies():
    mock_resp_ok = MagicMock()
    mock_resp_ok.status_code = 200
    mock_resp_ok.json.return_value = GREENHOUSE_RESPONSE
    mock_resp_ok.raise_for_status.return_value = None

    import requests

    def side_effect(url, **kwargs):
        if "good-company" in url:
            return mock_resp_ok
        raise requests.RequestException("Connection failed")

    with patch("collectors.greenhouse.requests.get", side_effect=side_effect):
        collector = GreenhouseCollector()
        jobs = collector.collect_all(["good-company", "bad-company"])

    assert len(jobs) == 1
