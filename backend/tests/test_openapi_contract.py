def test_openapi_docs_auth_refresh_error_envelope(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    refresh_post = schema["paths"]["/api/v1/auth/refresh"]["post"]
    responses = refresh_post["responses"]
    assert "200" in responses
    assert responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith("RefreshAccessTokenResponse")
    assert "401" in responses
    assert "application/json" in responses["401"]["content"]


def test_openapi_docs_repos_analyze_response_model(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    analyze_post = schema["paths"]["/api/v1/repos/analyze"]["post"]
    analyze_schema_ref = analyze_post["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert analyze_schema_ref.endswith("AnalyzeRepoResponse")
    assert "429" in analyze_post["responses"]


def test_openapi_docs_sse_status_contract(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    status_get = schema["paths"]["/api/v1/repos/{repo_id}/status"]["get"]
    content = status_get["responses"]["200"]["content"]
    assert "text/event-stream" in content
    example = content["text/event-stream"]["example"]
    assert "event: progress" in example
    assert "event: done" in example


def test_openapi_docs_lexical_search_contract(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    lexical_get = schema["paths"]["/api/v1/repos/{repo_id}/search/lexical"]["get"]
    assert "200" in lexical_get["responses"]
    assert "404" in lexical_get["responses"]


def test_openapi_docs_hybrid_search_contract(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    hybrid_get = schema["paths"]["/api/v1/repos/{repo_id}/search/hybrid"]["get"]
    assert "200" in hybrid_get["responses"]
    assert "502" in hybrid_get["responses"]


def test_openapi_docs_chat_message_stream_contract(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    message_post = schema["paths"]["/api/v1/chat/sessions/{session_id}/message"]["post"]
    assert "200" in message_post["responses"]
    assert "text/event-stream" in message_post["responses"]["200"]["content"]


def test_openapi_docs_error_schema_has_example(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    analyze_errors = schema["paths"]["/api/v1/repos/analyze"]["post"]["responses"]["400"]["content"]["application/json"][
        "schema"
    ]
    assert "example" in analyze_errors
    assert "error" in analyze_errors["example"]


def test_openapi_docs_analyze_has_request_and_response_examples(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    analyze_post = schema["paths"]["/api/v1/repos/analyze"]["post"]
    request_example = analyze_post["requestBody"]["content"]["application/json"]["example"]
    assert request_example["github_url"].startswith("https://github.com/")
    assert "force_reanalyze" in request_example

    success_example = analyze_post["responses"]["200"]["content"]["application/json"]["example"]
    assert "job_id" in success_example
    assert "repo_id" in success_example


def test_openapi_docs_share_and_chat_examples(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    share_post = schema["paths"]["/api/v1/export/{repo_id}/share"]["post"]
    assert "example" in share_post["requestBody"]["content"]["application/json"]
    assert "example" in share_post["responses"]["200"]["content"]["application/json"]

    share_public = schema["paths"]["/api/v1/share/{token}"]["get"]
    assert "example" in share_public["responses"]["200"]["content"]["application/json"]

    chat_create = schema["paths"]["/api/v1/chat/sessions"]["post"]
    assert "example" in chat_create["requestBody"]["content"]["application/json"]
    assert "example" in chat_create["responses"]["200"]["content"]["application/json"]

    chat_message = schema["paths"]["/api/v1/chat/sessions/{session_id}/message"]["post"]
    assert "example" in chat_message["requestBody"]["content"]["application/json"]
    stream_example = chat_message["responses"]["200"]["content"]["text/event-stream"]["example"]
    assert "event: delta" in stream_example
    assert "event: done" in stream_example
