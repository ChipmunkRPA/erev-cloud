"""Explicit preparer confirmation for modification fixtures, through the public commands."""

from typing import Any

from fastapi import FastAPI
from support.principals import Actor
from support.reference import get, patch, post


def confirm_answers(app: FastAPI, modification_id: str, author: Actor) -> dict[str, Any]:
    """Accept the displayed proposals, then classify the saved answers before previewing."""
    path = f"/api/v1/modifications/{modification_id}"
    classified = post(app, f"{path}/classify", author, {})
    assert classified.status_code == 200, classified.text
    if classified.json()["prefill_reasons"]:
        shown = get(app, path, author)
        assert shown.status_code == 200, shown.text
        saved = patch(
            app,
            path,
            author,
            {"questionnaire": classified.json()["questionnaire"]},
            if_match=shown.headers["ETag"],
        )
        assert saved.status_code == 200, saved.text
        classified = post(app, f"{path}/classify", author, {})
        assert classified.status_code == 200, classified.text
    assert classified.json()["prefill_reasons"] == {}, classified.text
    return dict(classified.json())
