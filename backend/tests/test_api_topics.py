"""Topics, sources, ingestion, and memory search over the API."""

from __future__ import annotations

import pytest

NOTES = """
We decided that invite links expire after 14 days.
Invites must not be reusable once an account is created.
There is a risk that expired invites fail silently and the user sees a blank page.
"""


async def _create_topic(client, name="customer onboarding"):
    response = await client.post("/topics", json={"name": name, "description": "everything onboarding"})
    assert response.status_code == 201
    return response.json()


async def test_create_and_list_topics(client):
    topic = await _create_topic(client)
    assert topic["name"] == "customer onboarding"

    listed = await client.get("/topics")
    assert listed.status_code == 200
    assert [t["id"] for t in listed.json()] == [topic["id"]]


async def test_duplicate_topic_name_is_rejected(client):
    await _create_topic(client)
    response = await client.post("/topics", json={"name": "customer onboarding"})
    assert response.status_code == 409


async def test_topic_detail_reports_counts(client):
    topic = await _create_topic(client)
    detail = await client.get(f"/topics/{topic['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["source_count"] == 0
    assert body["memory_count"] == 0
    assert body["memory_types"] == {}


async def test_unknown_topic_returns_404(client):
    response = await client.get("/topics/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_register_pasted_text_source(client):
    topic = await _create_topic(client)
    response = await client.post(
        f"/topics/{topic['id']}/sources",
        json={"type": "pasted_text", "name": "kickoff notes", "text": NOTES},
    )
    assert response.status_code == 201
    source = response.json()
    assert source["status"] == "registered"
    assert source["metadata_json"]["text"].strip().startswith("We decided")


async def test_pasted_text_without_text_is_rejected(client):
    topic = await _create_topic(client)
    response = await client.post(
        f"/topics/{topic['id']}/sources", json={"type": "pasted_text", "name": "empty"}
    )
    assert response.status_code == 422


async def test_local_file_without_uri_is_rejected(client):
    topic = await _create_topic(client)
    response = await client.post(
        f"/topics/{topic['id']}/sources", json={"type": "local_file", "name": "no uri"}
    )
    assert response.status_code == 422


async def test_unknown_source_type_is_rejected(client):
    topic = await _create_topic(client)
    response = await client.post(
        f"/topics/{topic['id']}/sources", json={"type": "carrier_pigeon", "name": "nope"}
    )
    assert response.status_code == 422


async def test_sync_ingestion_then_memory_search(client):
    topic = await _create_topic(client)
    created = await client.post(
        f"/topics/{topic['id']}/sources",
        json={"type": "pasted_text", "name": "kickoff notes", "text": NOTES},
    )
    source_id = created.json()["id"]

    ingested = await client.post(f"/sources/{source_id}/ingest?mode=sync")
    assert ingested.status_code == 200
    summary = ingested.json()["summary"]
    assert summary["status"] == "ingested"
    assert summary["memories_created"] > 0

    memories = await client.get(f"/topics/{topic['id']}/memories")
    assert memories.status_code == 200
    assert {m["type"] for m in memories.json()} >= {"decision", "constraint", "risk"}

    filtered = await client.get(f"/topics/{topic['id']}/memories?type=decision")
    assert all(m["type"] == "decision" for m in filtered.json())

    search = await client.post(
        "/memory/search", json={"query": "how long is an invite valid", "topic_id": topic["id"]}
    )
    assert search.status_code == 200
    body = search.json()
    assert body["count"] > 0
    assert "expire after 14 days" in body["results"][0]["memory"]["content"]
    assert body["weights"]["similarity"] > 0
    assert set(body["results"][0]["components"]) == set(body["weights"])

    detail = await client.get(f"/topics/{topic['id']}")
    assert detail.json()["memory_count"] == summary["memories_created"]
    assert detail.json()["chunk_count"] == summary["chunks_created"]


async def test_sync_ingestion_failure_reports_422(client):
    topic = await _create_topic(client)
    created = await client.post(
        f"/topics/{topic['id']}/sources",
        json={"type": "local_file", "name": "missing", "uri": "/nope/missing.md"},
    )
    response = await client.post(f"/sources/{created.json()['id']}/ingest?mode=sync")
    assert response.status_code == 422
    assert response.json()["summary"]["status"] == "failed"


async def test_async_ingestion_enqueues_a_job(client, monkeypatch):
    topic = await _create_topic(client)
    created = await client.post(
        f"/topics/{topic['id']}/sources",
        json={"type": "pasted_text", "name": "kickoff notes", "text": NOTES},
    )
    source_id = created.json()["id"]

    enqueued: list[tuple[str, dict]] = []

    async def fake_enqueue(job_type, payload=None):  # noqa: ANN001, ANN202
        enqueued.append((job_type, payload or {}))

        class Job:
            id = "job-1"

        return Job()

    monkeypatch.setattr("app.api.routes.sources.enqueue", fake_enqueue)

    response = await client.post(f"/sources/{source_id}/ingest")
    assert response.status_code == 202
    assert enqueued == [("ingest_source", {"source_id": source_id})]
    assert (await client.get(f"/sources/{source_id}")).json()["status"] == "ingesting"


async def test_ingestion_reports_503_when_the_queue_is_down(client, monkeypatch):
    topic = await _create_topic(client)
    created = await client.post(
        f"/topics/{topic['id']}/sources",
        json={"type": "pasted_text", "name": "kickoff notes", "text": NOTES},
    )

    async def broken_enqueue(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        raise ConnectionError("redis is down")

    monkeypatch.setattr("app.api.routes.sources.enqueue", broken_enqueue)
    response = await client.post(f"/sources/{created.json()['id']}/ingest")
    assert response.status_code == 503
    assert "mode=sync" in response.json()["detail"]


async def test_memory_search_rejects_unknown_types(client):
    response = await client.post("/memory/search", json={"query": "x", "types": ["nonsense"]})
    assert response.status_code == 422


async def test_memory_search_on_an_empty_store(client):
    response = await client.post("/memory/search", json={"query": "anything"})
    assert response.status_code == 200
    assert response.json()["count"] == 0
