import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.gmail.daily_email_summary import render_markdown


def test_render_markdown_uses_universal_mailto_links():
    result = {
        "summary": "",
        "counts": {
            "client_communications": 1,
            "records": 0,
            "appointments": 0,
            "refills": 0,
            "pet_questions": 0,
            "other": 0,
        },
        "client_communications": [
            {
                "message_id": "msg-1",
                "sender": "Example Sender",
                "email": "sender@example.com",
                "subject": "Please call me",
                "summary": "Needs a callback.",
                "unread": True,
                "reply": {
                    "message_id": "reply-1",
                    "summary": "Already replied.",
                },
            }
        ],
        "records": [],
        "appointments": [],
        "refills": [],
        "pet_questions": [],
        "other": [],
        "follow_up_notes": [],
    }

    rendered = render_markdown(result, "newer_than:1d", 1)

    assert "mail.google.com" not in rendered
    assert "mailto:sender%40example.com?subject=Please%20call%20me" in rendered
    assert "mailto:sender%40example.com?subject=Re%3A%20Please%20call%20me" in rendered
