import asyncio

import httpx
import pytest

from app.linkedin import (
    LinkedInProfileNotFoundError,
    LinkedInVerificationError,
    normalize_linkedin_url,
    verify_linkedin_profile,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            " https://linkedin.com/in/Ada-Lovelace/?trk=contact ",
            "https://www.linkedin.com/in/ada-lovelace",
        ),
        (
            "https://www.linkedin.com/in/grace-hopper#about",
            "https://www.linkedin.com/in/grace-hopper",
        ),
        (
            "HTTPS://WWW.LINKEDIN.COM/in/abc",
            "https://www.linkedin.com/in/abc",
        ),
    ],
)
def test_normalize_linkedin_url(value, expected):
    assert normalize_linkedin_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        None,
        "http://www.linkedin.com/in/ada-lovelace",
        "https://evil.example/in/ada-lovelace",
        "https://linkedin.com.evil.example/in/ada-lovelace",
        "https://user:password@linkedin.com/in/ada-lovelace",
        "https://linkedin.com:443/in/ada-lovelace",
        "https://www.linkedin.com/company/openai",
        "https://www.linkedin.com/in/a",
        "https://www.linkedin.com/in/" + "a" * 101,
        "https://www.linkedin.com/in/name/extra",
        "https://www.linkedin.com/in/name%2Fextra",
        "https://www.linkedin.com/in/ada lovelace",
        "https://linkedin.com/foo/../in/ada-lovelace",
        "https://linkedin.com\\@evil.example/in/ada-lovelace",
    ],
)
def test_normalize_linkedin_url_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        normalize_linkedin_url(value)


def test_verify_linkedin_profile_accepts_success_statuses():
    for status_code in (200, 204):
        transport = httpx.MockTransport(
            lambda request, code=status_code: httpx.Response(code, request=request)
        )
        asyncio.run(
            verify_linkedin_profile(
                "https://www.linkedin.com/in/ada-lovelace",
                transport=transport,
            )
        )


@pytest.mark.parametrize("status_code", [404, 410])
def test_verify_linkedin_profile_rejects_missing_profiles(status_code):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status_code, request=request)
    )
    with pytest.raises(LinkedInProfileNotFoundError):
        asyncio.run(
            verify_linkedin_profile(
                "https://www.linkedin.com/in/missing-profile",
                transport=transport,
            )
        )


def test_verify_linkedin_profile_detects_404_after_safe_redirect():
    request_count = 0

    def redirect_then_missing(request):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(302, headers={"location": "/in/missing-profile/"})
        return httpx.Response(404, request=request)

    with pytest.raises(LinkedInProfileNotFoundError):
        asyncio.run(
            verify_linkedin_profile(
                "https://www.linkedin.com/in/missing-profile",
                transport=httpx.MockTransport(redirect_then_missing),
            )
        )


def test_verify_linkedin_profile_rejects_external_redirects():
    requested_hosts = []

    def redirect_external(request):
        requested_hosts.append(request.url.host)
        return httpx.Response(
            302,
            headers={"location": "https://internal.example/secret"},
            request=request,
        )

    with pytest.raises(LinkedInVerificationError):
        asyncio.run(
            verify_linkedin_profile(
                "https://www.linkedin.com/in/ada-lovelace",
                transport=httpx.MockTransport(redirect_external),
            )
        )
    assert requested_hosts == ["www.linkedin.com"]


@pytest.mark.parametrize("status_code", [400, 401, 403, 429, 500, 999])
def test_verify_linkedin_profile_fails_closed_on_inconclusive_status(status_code):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status_code, request=request)
    )
    with pytest.raises(LinkedInVerificationError):
        asyncio.run(
            verify_linkedin_profile(
                "https://www.linkedin.com/in/ada-lovelace",
                transport=transport,
            )
        )


def test_verify_linkedin_profile_reports_network_failures():
    def fail(request):
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(LinkedInVerificationError):
        asyncio.run(
            verify_linkedin_profile(
                "https://www.linkedin.com/in/ada-lovelace",
                transport=httpx.MockTransport(fail),
            )
        )
