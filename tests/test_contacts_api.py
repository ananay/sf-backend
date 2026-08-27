BASE = "/api/v1/contacts"
PNG_DATA_URI = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "sqlite"


def test_create_contact(client, payload):
    response = client.post(BASE, json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["email"] == "ada@example.com"
    assert body["full_name"] == "Ada Lovelace"
    assert body["created_at"] and body["updated_at"]
    assert body["addresses"][0]["type"] == "Work"
    assert body["addresses"][0]["id"] > 0


def test_contact_supports_multiple_typed_addresses(client, payload):
    addresses = [
        {"type": "Home", "address": "12 Home St", "city": "London"},
        {"type": "Work", "address": "34 Work Ave", "city": "London"},
        {"type": "Other", "address": "PO Box 56"},
    ]

    response = client.post(BASE, json={**payload, "addresses": addresses})

    assert response.status_code == 201
    assert [item["type"] for item in response.json()["addresses"]] == ["Home", "Work", "Other"]
    assert len({item["id"] for item in response.json()["addresses"]}) == 3


def test_contact_rejects_invalid_or_blank_address(client, payload):
    invalid_type = [{"type": "Vacation", "address": "1 Beach Rd"}]
    blank_street = [{"type": "Home", "address": "   "}]

    assert client.post(BASE, json={**payload, "addresses": invalid_type}).status_code == 422
    assert client.post(BASE, json={**payload, "addresses": blank_street}).status_code == 422


def test_create_contact_with_photo(client, payload):
    response = client.post(BASE, json={**payload, "photo": PNG_DATA_URI})

    assert response.status_code == 201
    assert response.json()["photo"] == PNG_DATA_URI


def test_create_rejects_invalid_photo(client, payload):
    wrong_type = "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="
    mismatched_content = "data:image/png;base64,SGVsbG8="

    assert client.post(BASE, json={**payload, "photo": wrong_type}).status_code == 422
    assert client.post(BASE, json={**payload, "photo": mismatched_content}).status_code == 422


def test_create_requires_valid_email(client, payload):
    response = client.post(BASE, json={**payload, "email": "not-an-email"})
    assert response.status_code == 422


def test_create_requires_names(client, payload):
    response = client.post(BASE, json={**payload, "first_name": ""})
    assert response.status_code == 422


def test_create_requires_linkedin_url(client, payload, linkedin_verifier):
    response = client.post(
        BASE,
        json={
            key: value for key, value in payload.items() if key != "linkedin_url"
        },
    )
    assert response.status_code == 422
    linkedin_verifier.assert_not_awaited()


def test_create_normalizes_and_verifies_linkedin_url(client, payload, linkedin_verifier):
    response = client.post(
        BASE,
        json={
            **payload,
            "linkedin_url": " https://linkedin.com/in/Ada-Lovelace/?trk=contact ",
        },
    )
    assert response.status_code == 201
    expected = "https://www.linkedin.com/in/ada-lovelace"
    assert response.json()["linkedin_url"] == expected
    linkedin_verifier.assert_awaited_once_with(expected)


def test_create_rejects_malformed_linkedin_urls(client, payload, linkedin_verifier):
    invalid_urls = [
        "",
        "https://example.com/in/ada-lovelace",
        "https://www.linkedin.com/company/openai",
    ]
    for index, linkedin_url in enumerate(invalid_urls):
        response = client.post(
            BASE,
            json={**payload, "email": f"ada{index}@example.com", "linkedin_url": linkedin_url},
        )
        assert response.status_code == 422
    linkedin_verifier.assert_not_awaited()


def test_create_rejects_confirmed_missing_linkedin_profile(
    client, payload, linkedin_verifier
):
    from app.linkedin import LinkedInProfileNotFoundError

    linkedin_verifier.side_effect = LinkedInProfileNotFoundError(
        "LinkedIn profile was not found"
    )
    response = client.post(BASE, json=payload)
    assert response.status_code == 422
    issue = response.json()["detail"][0]
    assert issue["loc"] == ["body", "linkedin_url"]


def test_create_fails_closed_when_linkedin_is_unreachable(
    client, payload, linkedin_verifier
):
    from app.linkedin import LinkedInVerificationError

    linkedin_verifier.side_effect = LinkedInVerificationError(
        "LinkedIn could not be reached to verify this profile"
    )
    response = client.post(BASE, json=payload)
    assert response.status_code == 503


def test_duplicate_email_conflicts(client, payload):
    assert client.post(BASE, json=payload).status_code == 201
    response = client.post(BASE, json={**payload, "email": "ADA@example.com"})
    assert response.status_code == 409


def test_get_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.get(f"{BASE}/{contact_id}")
    assert response.status_code == 200
    assert response.json()["id"] == contact_id


def test_get_missing_contact_returns_404(client):
    assert client.get(f"{BASE}/9999").status_code == 404


def test_list_pagination_and_total(client, payload):
    for index in range(5):
        client.post(BASE, json={**payload, "email": f"user{index}@example.com"})

    response = client.get(BASE, params={"limit": 2, "offset": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["limit"] == 2 and body["offset"] == 2


def test_list_search(client, payload):
    client.post(BASE, json=payload)
    client.post(
        BASE,
        json={**payload, "first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com", "company": "US Navy"},
    )

    hits = client.get(BASE, params={"search": "hopper"}).json()
    assert hits["total"] == 1
    assert hits["items"][0]["last_name"] == "Hopper"

    by_company = client.get(BASE, params={"search": "navy"}).json()
    assert by_company["total"] == 1

    misses = client.get(BASE, params={"search": "nobody"}).json()
    assert misses["total"] == 0


def test_list_sorting(client, payload):
    client.post(BASE, json={**payload, "last_name": "Zhang", "email": "z@example.com"})
    client.post(BASE, json={**payload, "last_name": "Adams", "email": "a@example.com"})

    names = [
        item["last_name"]
        for item in client.get(BASE, params={"sort_by": "last_name", "order": "asc"}).json()["items"]
    ]
    assert names == ["Adams", "Zhang"]


def test_list_rejects_bad_sort_field(client):
    assert client.get(BASE, params={"sort_by": "; DROP TABLE contacts"}).status_code == 422


def test_patch_updates_only_sent_fields(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"phone": "+1-000-000-0000"})
    assert response.status_code == 200
    body = response.json()
    assert body["phone"] == "+1-000-000-0000"
    assert body["first_name"] == "Ada"
    assert body["company"] == "Analytical Engines"
    assert len(body["addresses"]) == 1


def test_patch_replaces_or_clears_addresses(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    replacement = [{"type": "Home", "address": "99 New St"}]

    replaced = client.patch(f"{BASE}/{contact_id}", json={"addresses": replacement})
    cleared = client.patch(f"{BASE}/{contact_id}", json={"addresses": []})

    assert replaced.status_code == 200
    assert replaced.json()["addresses"][0]["address"] == "99 New St"
    assert cleared.status_code == 200
    assert cleared.json()["addresses"] == []


def test_photo_can_be_added_and_cleared_with_patch(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]

    added = client.patch(f"{BASE}/{contact_id}", json={"photo": PNG_DATA_URI})
    cleared = client.patch(f"{BASE}/{contact_id}", json={"photo": None})

    assert added.status_code == 200
    assert added.json()["photo"] == PNG_DATA_URI
    assert cleared.status_code == 200
    assert cleared.json()["photo"] is None


def test_patch_rejects_empty_linkedin_url(client, payload, linkedin_verifier):
    contact_id = client.post(BASE, json=payload).json()["id"]
    linkedin_verifier.reset_mock()

    assert client.patch(f"{BASE}/{contact_id}", json={"linkedin_url": ""}).status_code == 422
    assert client.patch(f"{BASE}/{contact_id}", json={"linkedin_url": None}).status_code == 422
    linkedin_verifier.assert_not_awaited()


def test_patch_normalizes_and_verifies_linkedin_url(
    client, payload, linkedin_verifier
):
    contact_id = client.post(BASE, json=payload).json()["id"]
    linkedin_verifier.reset_mock()

    response = client.patch(
        f"{BASE}/{contact_id}",
        json={"linkedin_url": "https://linkedin.com/in/Grace-Hopper/?trk=contact"},
    )
    expected = "https://www.linkedin.com/in/grace-hopper"
    assert response.status_code == 200
    assert response.json()["linkedin_url"] == expected
    linkedin_verifier.assert_awaited_once_with(expected)


def test_patch_other_fields_does_not_reverify_linkedin(
    client, payload, linkedin_verifier
):
    contact_id = client.post(BASE, json=payload).json()["id"]
    linkedin_verifier.reset_mock()

    response = client.patch(
        f"{BASE}/{contact_id}", json={"company": "New company"}
    )
    assert response.status_code == 200
    linkedin_verifier.assert_not_awaited()


def test_patch_duplicate_email_conflicts(client, payload):
    first = client.post(BASE, json=payload).json()["id"]
    client.post(BASE, json={**payload, "email": "grace@example.com"})
    response = client.patch(f"{BASE}/{first}", json={"email": "grace@example.com"})
    assert response.status_code == 409


def test_patch_same_email_is_allowed(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"email": payload["email"]})
    assert response.status_code == 200


def test_put_replaces_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.put(
        f"{BASE}/{contact_id}",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "grace@example.com",
            "linkedin_url": "https://www.linkedin.com/in/grace-hopper",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Grace Hopper"
    assert body["company"] is None  # omitted fields are cleared by PUT


def test_put_missing_contact_returns_404(client):
    response = client.put(
        f"{BASE}/9999",
        json={
            "first_name": "A",
            "last_name": "B",
            "email": "ab@example.com",
            "linkedin_url": "https://www.linkedin.com/in/example-profile",
        },
    )
    assert response.status_code == 404


def test_delete_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    assert client.delete(f"{BASE}/{contact_id}").status_code == 204
    assert client.get(f"{BASE}/{contact_id}").status_code == 404
    assert client.delete(f"{BASE}/{contact_id}").status_code == 404


def test_root_lists_entrypoints(client):
    body = client.get("/").json()
    assert body["contacts"] == BASE
