import re
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

LINKEDIN_URL_MAX_LENGTH = 500
_PROFILE_PATH = re.compile(r"^/in/([A-Za-z0-9][A-Za-z0-9-]{1,98}[A-Za-z0-9])/?$")
_ALLOWED_HOSTS = {"linkedin.com", "www.linkedin.com"}
_MAX_REDIRECTS = 3


class LinkedInProfileNotFoundError(Exception):
    """Raised when LinkedIn confirms that a profile does not exist."""


class LinkedInVerificationError(Exception):
    """Raised when LinkedIn cannot be reached to verify a profile."""


def normalize_linkedin_url(value: object) -> str:
    """Validate and canonicalize a public LinkedIn profile URL."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("LinkedIn URL is required")

    candidate = value.strip()
    if len(candidate) > LINKEDIN_URL_MAX_LENGTH:
        raise ValueError(f"LinkedIn URL must be {LINKEDIN_URL_MAX_LENGTH} characters or fewer")
    if any(character.isspace() for character in candidate) or "\\" in candidate:
        raise ValueError("LinkedIn URL cannot contain whitespace or backslashes")

    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as error:
        raise ValueError("Enter a valid LinkedIn profile URL") from error

    if parsed.scheme.lower() != "https":
        raise ValueError("LinkedIn URL must use HTTPS")
    if parsed.hostname is None or parsed.hostname.lower() not in _ALLOWED_HOSTS:
        raise ValueError("Enter a linkedin.com profile URL")
    if parsed.username or parsed.password or port is not None:
        raise ValueError("Enter a standard LinkedIn profile URL without credentials or a port")

    match = _PROFILE_PATH.fullmatch(parsed.path)
    if not match:
        raise ValueError("LinkedIn URL must look like https://www.linkedin.com/in/profile-name")

    slug = match.group(1).lower()
    return urlunsplit(("https", "www.linkedin.com", f"/in/{slug}", "", ""))


async def verify_linkedin_profile(
    url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Reject confirmed missing profiles and fail closed when verification is unavailable."""
    timeout = httpx.Timeout(5.0, connect=3.0)
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            transport=transport,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/124 Safari/537.36"
                ),
            },
        ) as client:
            current_url = url
            for redirect_count in range(_MAX_REDIRECTS + 1):
                async with client.stream("GET", current_url) as response:
                    if response.status_code in {404, 410}:
                        raise LinkedInProfileNotFoundError("LinkedIn profile was not found")
                    location = response.headers.get("location")
                    if not response.is_redirect:
                        if 200 <= response.status_code < 300:
                            return
                        raise LinkedInVerificationError(
                            "LinkedIn did not provide a verifiable profile response "
                            f"(status {response.status_code})"
                        )
                    if not location:
                        raise LinkedInVerificationError(
                            "LinkedIn returned a redirect without a destination"
                        )

                redirect_url = urljoin(current_url, location)
                try:
                    parsed_redirect = urlsplit(redirect_url)
                    redirect_port = parsed_redirect.port
                except ValueError:
                    raise LinkedInVerificationError(
                        "LinkedIn returned an invalid redirect while verifying this profile"
                    )
                if (
                    parsed_redirect.scheme.lower() != "https"
                    or parsed_redirect.hostname not in _ALLOWED_HOSTS
                    or parsed_redirect.username
                    or parsed_redirect.password
                    or redirect_port is not None
                ):
                    raise LinkedInVerificationError(
                        "LinkedIn redirected outside its trusted profile service"
                    )
                if redirect_count == _MAX_REDIRECTS:
                    raise LinkedInVerificationError(
                        "LinkedIn returned too many redirects while verifying this profile"
                    )
                current_url = redirect_url
    except LinkedInProfileNotFoundError:
        raise
    except httpx.RequestError as error:
        raise LinkedInVerificationError(
            "LinkedIn could not be reached to verify this profile"
        ) from error
