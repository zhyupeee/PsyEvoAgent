"""Compatibility of old persistent start fingerprints after adding branch inputs."""

import json

import pytest
from pydantic import ValidationError

from app.runs import Start


def test_step05_start_fingerprint_is_unchanged() -> None:
    prior = (
        '{"expected_version":1,"input":{"message":"合成输入"},'
        '"expected_session_version":1,"client_message_id":"original-key",'
        '"grant_ids":[],"initiation":"user"}'
    )
    body = Start.model_validate_json(prior)
    assert body.model_dump_json() == prior
    assert body.model_dump() == json.loads(prior)
    for invalid in [
        {},
        {"message": "", "source_message_id": "id"},
        {"message": "text", "source_message_id": "id"},
    ]:
        with pytest.raises(ValidationError):
            Start.model_validate({**json.loads(prior), "input": invalid})
