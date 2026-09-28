from scripts.gmail.evhstaff_gmail_inventory import parse_oauth_callback


def test_parse_oauth_callback_accepts_authorization_response():
    assert parse_oauth_callback("/?code=auth-code&state=expected-state") == {
        "code": ["auth-code"],
        "state": ["expected-state"],
    }


def test_parse_oauth_callback_ignores_browser_follow_up_requests():
    assert parse_oauth_callback("/favicon.ico") is None
    assert parse_oauth_callback("/") is None


def test_parse_oauth_callback_accepts_provider_error():
    assert parse_oauth_callback("/?error=access_denied&state=expected-state") == {
        "error": ["access_denied"],
        "state": ["expected-state"],
    }
