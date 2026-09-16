"""Offline installer identity, IAM and bounded retry contracts."""

import base64
import copy
import json
import uuid
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlsplit

import pytest
from azure.core.exceptions import HttpResponseError, ServiceRequestError

from azure_bing_assistant import installer_access as access
from azure_bing_assistant.agent import SourcePolicyError
from azure_bing_assistant.provision import AzureArmClient, ProvisioningError

SUB = "11111111-1111-1111-1111-111111111111"
OID = "22222222-2222-2222-2222-222222222222"
TENANT = "33333333-3333-3333-3333-333333333333"
GROUP = "rg-demo"
ENDPOINT = "https://ai-demo-offline.services.ai.azure.com/api/projects/project"
SCOPE, ACCOUNT, DOMAIN = access.project_scope(SUB, GROUP, ENDPOINT)
COLLECTION = SCOPE + "/providers/Microsoft.Authorization/roleAssignments"
ROLE = f"/subscriptions/{SUB}/providers/Microsoft.Authorization/roleDefinitions/{access.FOUNDRY_USER_ROLE_ID}"


def token(oid=OID, tenant=TENANT):
    payload = base64.urlsafe_b64encode(json.dumps({"oid": oid, "tid": tenant}).encode()).decode().rstrip("=")
    return "header." + payload + ".signature"


def forbidden(status=403):
    error = HttpResponseError("PRIVATE_PROVIDER_BODY token=PRIVATE_TOKEN")
    error.status_code = status
    return error


def wrapped(status=403):
    error = SourcePolicyError("safe wrapper")
    error.__cause__ = forbidden(status)
    return error


def project_pending(message="Project not found", code="NotFound"):
    error = forbidden(404)
    error.error = SimpleNamespace(code=code, message=message)
    result = SourcePolicyError("safe wrapper")
    result.__cause__ = error
    return result


def assignment(name=None, **properties):
    return {
        "id": COLLECTION + "/" + (name or str(uuid.uuid4())),
        "properties": {"principalId": OID, "scope": SCOPE, "roleDefinitionId": ROLE, **properties},
    }


class Clock:
    def __init__(self):
        self.now = 0
        self.waits = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


class Arm:
    def __init__(self):
        self.calls = []
        self.items = []
        self.closed = False
        self.subscription = {"tenantId": TENANT}
        self.project = {"id": SCOPE}
        self.account = {"id": ACCOUNT, "properties": {"customSubDomainName": DOMAIN}}
        self.put_status = 201
        self.put_error = None
        self.list_status = 200
        self.extra_list = {}
        self.confirm_wrong = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def _send_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        assert kwargs["retry_total"] == 0
        path = urlsplit(url).path
        if method == "PUT":
            body = kwargs["body"]["properties"]
            assert set(body) == {"principalId", "roleDefinitionId"}
            assert body == {"principalId": OID, "roleDefinitionId": ROLE}
            assert path.startswith(COLLECTION + "/")
            if self.put_status != 403:
                self.items.append({"id": path, "properties": {**body, "scope": SCOPE}})
            if self.put_error:
                raise self.put_error
            return self.put_status, {}, {}
        assert method == "GET"
        if path == f"/subscriptions/{SUB}":
            assert url.endswith("api-version=2022-12-01")
            return 200, self.subscription, {}
        if path in {SCOPE, ACCOUNT}:
            assert url.endswith("api-version=2025-06-01")
            return 200, self.project if path == SCOPE else self.account, {}
        assert "api-version=2022-04-01" in url
        if path == COLLECTION:
            return self.list_status, {"value": copy.deepcopy(self.items), **self.extra_list}, {}
        for item in self.items:
            if item["id"].casefold() == path.casefold():
                result = copy.deepcopy(item)
                if self.confirm_wrong:
                    result["properties"]["principalId"] = TENANT
                return 200, result, {}
        return 404, {}, {}


@pytest.fixture
def context(monkeypatch):
    credential = Mock(spec=["get_token", "close"])
    credential.get_token.return_value = SimpleNamespace(token=token())
    arm = Arm()
    factory = Mock(return_value=arm)
    monkeypatch.setattr(access, "AzureArmClient", factory)
    clock = Clock()
    monkeypatch.setattr(access.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(access.time, "sleep", clock.sleep)
    output = []

    def configure(callback):
        return access.configure_with_project_access(
            callback, credential, SUB, GROUP, ENDPOINT, "en", output.append,
        )

    return SimpleNamespace(
        credential=credential, arm=arm, factory=factory, clock=clock, output=output,
        configure=configure,
    )


def test_existing_working_access_is_a_single_probe_without_any_identity_or_iam_calls(context):
    callback = Mock(return_value="done")
    assert context.configure(callback) == "done"
    callback.assert_called_once_with(60)
    context.factory.assert_not_called()
    context.credential.get_token.assert_not_called()
    assert context.output == []


def test_new_project_readiness_wait_verifies_arm_without_granting_a_role(context):
    callback = Mock(side_effect=[project_pending(), "done"])
    assert context.configure(callback) == "done"
    assert context.clock.now == 15
    assert len(context.arm.calls) == 3
    assert all(call[0] == "GET" for call in context.arm.calls)
    assert not context.arm.items


def test_new_project_readiness_then_403_grants_access_only_after_denial(context):
    callback = Mock(side_effect=[project_pending(), wrapped(), "done"])
    assert context.configure(callback) == "done"
    assert context.factory.call_count == 2
    assert sum(call[0] == "PUT" for call in context.arm.calls) == 1
    assert callback.call_count == 3 and context.clock.now == 30


def test_project_readiness_after_grant_does_not_duplicate_assignment(context):
    callback = Mock(side_effect=[wrapped(), project_pending(), "done"])
    assert context.configure(callback) == "done"
    assert sum(call[0] == "PUT" for call in context.arm.calls) == 1


@pytest.mark.parametrize("error", [
    wrapped(404),
    project_pending("Model deployment not found"),
    project_pending(code="OtherNotFound"),
    SourcePolicyError("Project not found"),
])
def test_arbitrary_not_found_is_not_retried_or_granted(context, error):
    callback = Mock(side_effect=error)
    with pytest.raises(type(error)) as caught:
        context.configure(callback)
    assert caught.value is error
    context.factory.assert_not_called()
    assert context.clock.now == 0


def test_missing_arm_project_does_not_turn_data_404_into_a_retry_loop(context):
    context.arm.project = {"id": SCOPE + "-other"}
    callback = Mock(side_effect=project_pending())
    with pytest.raises(access.InstallerAccessError):
        context.configure(callback)
    callback.assert_called_once()
    assert context.clock.now == 0
    assert not context.arm.items


def test_project_readiness_wait_is_bounded_without_iam_writes(context):
    callback = Mock(side_effect=project_pending())
    with pytest.raises(access.InstallerAccessError) as caught:
        context.configure(callback)
    assert caught.value.message == access.PROJECT_TIMEOUT
    assert context.clock.now == 600
    assert callback.call_count == 40
    assert all(call[0] == "GET" for call in context.arm.calls)


def test_readonly_probe_reveals_permission_denial_hidden_by_create_404(context):
    callback = Mock(side_effect=[project_pending(), "done"])
    probe = Mock(side_effect=wrapped())
    assert access.configure_with_project_access(
        callback, context.credential, SUB, GROUP, ENDPOINT, "en", context.output.append,
        probe_access=probe,
    ) == "done"
    probe.assert_called_once_with(60)
    assert sum(call[0] == "PUT" for call in context.arm.calls) == 1
    assert context.clock.now == 15


def test_successful_readonly_probe_never_causes_a_grant_for_404(context):
    callback = Mock(side_effect=[project_pending(), "done"])
    probe = Mock()
    assert access.configure_with_project_access(
        callback, context.credential, SUB, GROUP, ENDPOINT, "en", context.output.append,
        probe_access=probe,
    ) == "done"
    assert not context.arm.items
    assert all(call[0] == "GET" for call in context.arm.calls)


def test_real_sdk_readonly_probe_preserves_403_and_never_posts(context):
    from azure.ai.projects import AIProjectClient
    from azure.core.credentials import AccessToken
    from azure_bing_assistant.agent import FoundrySdkWriter
    from test_web_policy import AgentTransport, JsonResponse

    class DeniedRead(AgentTransport):
        def send(self, request, **kwargs):
            self.requests.append(request)
            assert request.method == "GET"
            assert urlsplit(request.url).path.endswith("/agents")
            assert 0 < kwargs["connection_timeout"] <= 30
            assert 0 < kwargs["read_timeout"] <= 30
            return JsonResponse(request, {"error": {"code": "UserError", "message": "PRIVATE"}}, status=403)

    context.credential.get_token.return_value = AccessToken(token(), 9999999999)
    transport = DeniedRead()
    with AIProjectClient(endpoint=ENDPOINT, credential=context.credential, transport=transport) as project:
        writer = FoundrySdkWriter(ENDPOINT, context.credential, "chat-model", project_client=project)
        with pytest.raises(SourcePolicyError) as caught:
            writer.probe_project_access(60)
    assert access._is_forbidden(caught.value)
    assert len(transport.requests) == 1
    assert "PRIVATE" not in str(caught.value)


def test_late_probe_denial_cannot_start_iam_repair_at_deadline(context):
    callback = Mock(side_effect=project_pending())

    def probe(_budget):
        context.clock.now = 600
        raise wrapped()

    with pytest.raises(access.InstallerAccessError):
        access.configure_with_project_access(
            callback, context.credential, SUB, GROUP, ENDPOINT, "en", context.output.append,
            probe_access=probe,
        )
    assert not context.arm.items
    assert all(call[0] == "GET" for call in context.arm.calls)
    assert context.factory.call_count == 1


def test_late_create_denial_cannot_start_iam_repair_at_deadline(context):
    calls = [0]

    def callback(_budget):
        calls[0] += 1
        if calls[0] == 1:
            raise project_pending()
        context.clock.now = 600
        raise wrapped()

    with pytest.raises(access.InstallerAccessError):
        context.configure(callback)
    assert not context.arm.items
    assert context.factory.call_count == 1


def test_iam_budget_is_checked_before_role_assignment_put(context):
    original = context.arm._send_json

    def request(method, url, **kwargs):
        assert 0 < kwargs["request_timeout"] <= 10
        response = original(method, url, **kwargs)
        if method == "GET" and urlsplit(url).path.startswith(COLLECTION + "/"):
            context.clock.now = 10
        return response

    context.arm._send_json = request
    with pytest.raises(access.InstallerAccessError):
        access._repair(context.credential, SUB, GROUP, ENDPOINT, deadline=10)
    assert not context.arm.items
    assert all(call[0] == "GET" for call in context.arm.calls)


@pytest.mark.parametrize("first", [forbidden(), wrapped()])
def test_grant_binds_same_sdk_identity_tenant_endpoint_and_exact_scope(context, first):
    callback = Mock(side_effect=[first, "done"])
    assert context.configure(callback) == "done"
    context.factory.assert_called_once_with(credential=context.credential)
    assert [call.args[0] for call in context.credential.get_token.call_args_list] == [access.ARM_SCOPE, access.FOUNDRY_SCOPE]
    puts = [call for call in context.arm.calls if call[0] == "PUT"]
    assert len(puts) == 1
    assert urlsplit(puts[0][1]).path.startswith(COLLECTION + "/")
    assert callback.call_count == 2 and context.clock.now == 15
    assert context.arm.closed
    context.credential.close.assert_not_called()
    assert "PRIVATE" not in "\n".join(context.output)


@pytest.mark.parametrize("error", [
    forbidden(401), forbidden(400), forbidden(429), forbidden(500),
    wrapped(401), wrapped(400), wrapped(429),
    SourcePolicyError("403 in prose only"), ServiceRequestError("transport"),
    ValueError("other"), KeyboardInterrupt(),
])
def test_non_explicit_403_never_retries_or_accesses_iam(context, error):
    callback = Mock(side_effect=error)
    with pytest.raises(type(error)) as caught:
        context.configure(callback)
    assert caught.value is error
    callback.assert_called_once()
    context.factory.assert_not_called()
    context.credential.get_token.assert_not_called()


def test_implicit_context_does_not_authorize_iam(context):
    error = SourcePolicyError("safe")
    error.__context__ = forbidden()
    with pytest.raises(SourcePolicyError):
        context.configure(Mock(side_effect=error))
    context.factory.assert_not_called()


@pytest.mark.parametrize("jwt", [
    "", "opaque-token", "header.%%%%.signature", "h." + "a" * 17000 + ".s",
    token(oid="not-a-uuid"), token(tenant="not-a-uuid"),
    "h." + base64.urlsafe_b64encode(b'{"oid":"x","oid":"y"}').decode().rstrip("=") + ".s",
])
def test_malformed_credential_tokens_fail_closed_without_raw_content(context, jwt):
    context.credential.get_token.return_value.token = jwt
    with pytest.raises(access.InstallerAccessError) as caught:
        context.configure(Mock(side_effect=forbidden()))
    context.factory.assert_not_called()
    assert "PRIVATE" not in str(caught.value)
    if jwt:
        assert jwt not in str(caught.value)


def test_same_credential_cannot_repair_different_foundry_identity(context):
    context.credential.get_token.side_effect = [
        SimpleNamespace(token=token()), SimpleNamespace(token=token(oid=TENANT)),
    ]
    with pytest.raises(access.InstallerAccessError):
        context.configure(Mock(side_effect=forbidden()))
    context.factory.assert_not_called()


@pytest.mark.parametrize("subscription,group,endpoint", [
    ("other", GROUP, ENDPOINT), (SUB, "rg/other", ENDPOINT),
    (SUB, GROUP, ENDPOINT + "?sig=SECRET"), (SUB, GROUP, ENDPOINT + "/../other"),
    (SUB, GROUP, ENDPOINT.replace("https:", "http:")),
    (SUB, GROUP, ENDPOINT.replace("services.ai.azure.com", "services.ai.azure.com.evil")),
    (SUB, GROUP, ENDPOINT.replace("project", "%70roject")),
    (SUB, GROUP, ENDPOINT.replace("https://", "https://user:SECRET@")),
])
def test_invalid_scope_or_endpoint_prevents_identity_and_iam_requests(context, subscription, group, endpoint):
    with pytest.raises(access.InstallerAccessError):
        access.configure_with_project_access(
            Mock(side_effect=forbidden()), context.credential, subscription, group,
            endpoint, "en", context.output.append,
        )
    context.factory.assert_not_called()
    context.credential.get_token.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("subscription", {"tenantId": OID}), ("project", {"id": ACCOUNT + "/projects/other"}),
    ("account", {"id": ACCOUNT, "properties": {"customSubDomainName": "other"}}),
    ("account", {"id": ACCOUNT + "other", "properties": {"customSubDomainName": DOMAIN}}),
])
def test_arm_verification_mismatch_never_writes_iam(context, field, value):
    setattr(context.arm, field, value)
    with pytest.raises(access.InstallerAccessError):
        context.configure(Mock(side_effect=forbidden()))
    assert not any(method == "PUT" for method, *_ in context.arm.calls)


def test_existing_manual_assignment_is_respected_and_confirmed(context):
    item = assignment()
    context.arm.items = [item]
    assert context.configure(Mock(side_effect=[forbidden(), "done"])) == "done"
    assert not any(method == "PUT" for method, *_ in context.arm.calls)
    assert any(item["id"] in url for _, url, _ in context.arm.calls)


def test_second_failed_access_probe_reuses_the_confirmed_deterministic_assignment(context):
    assert context.configure(Mock(side_effect=[forbidden(), "first"])) == "first"
    assert context.configure(Mock(side_effect=[forbidden(), "second"])) == "second"
    assert sum(method == "PUT" for method, *_ in context.arm.calls) == 1


def test_inherited_or_unrelated_assignment_is_not_mistaken_for_project_grant(context):
    context.arm.items = [assignment(scope=ACCOUNT), assignment(roleDefinitionId=ROLE + "other")]
    assert context.configure(Mock(side_effect=[forbidden(), "done"])) == "done"
    puts = [call for call in context.arm.calls if call[0] == "PUT"]
    assert len(puts) == 1 and COLLECTION + "/" in puts[0][1]


@pytest.mark.parametrize("properties", [
    {"condition": "true"}, {"condition": "@Resource[example]"},
])
def test_conditional_grant_is_not_bypassed(context, properties):
    context.arm.items = [assignment(**properties)]
    with pytest.raises(access.InstallerAccessError, match="conditional"):
        context.configure(Mock(side_effect=forbidden()))
    assert not any(method == "PUT" for method, *_ in context.arm.calls)


def test_conflicting_deterministic_assignment_is_not_overwritten(context):
    name = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{SCOPE.lower()}|{OID}|{access.FOUNDRY_USER_ROLE_ID}"))
    context.arm.items = [assignment(name, principalId=TENANT)]
    with pytest.raises(access.InstallerAccessError, match="conflicts"):
        context.configure(Mock(side_effect=forbidden()))
    assert not any(method == "PUT" for method, *_ in context.arm.calls)


@pytest.mark.parametrize("ambiguous", [False, True])
def test_409_or_ambiguous_put_only_reconciles_read_only_without_duplicate(context, ambiguous):
    context.arm.put_status = 409
    if ambiguous:
        context.arm.put_error = ProvisioningError("PRIVATE transport error")
    assert context.configure(Mock(side_effect=[forbidden(), "done"])) == "done"
    assert sum(method == "PUT" for method, *_ in context.arm.calls) == 1
    assert sum(urlsplit(url).path == COLLECTION for _, url, _ in context.arm.calls) == 2


def test_ambiguous_put_without_matching_read_only_evidence_fails_closed(context):
    original = context.arm._send_json
    def request(method, url, **kwargs):
        if method == "PUT":
            context.arm.calls.append((method, url, kwargs))
            raise ProvisioningError("PRIVATE transport failure")
        return original(method, url, **kwargs)
    context.arm._send_json = request
    callback = Mock(side_effect=forbidden())
    with pytest.raises(access.InstallerAccessError, match="no duplicate assignment"):
        context.configure(callback)
    assert sum(method == "PUT" for method, *_ in context.arm.calls) == 1
    assert callback.call_count == 1


@pytest.mark.parametrize("permission", ["list_status", "put_status"])
def test_denied_iam_explains_admin_action_and_never_broadens_scope(context, permission):
    setattr(context.arm, permission, 403)
    callback = Mock(side_effect=forbidden())
    with pytest.raises(access.InstallerAccessError, match="roleAssignments/write") as caught:
        context.configure(callback)
    assert "User Access Administrator" in str(caught.value)
    assert callback.call_count == 1 and context.clock.now == 0
    assert all(COLLECTION + "/" in url for method, url, _ in context.arm.calls if method == "PUT")


def test_confirmed_grant_must_match_principal(context):
    context.arm.confirm_wrong = True
    with pytest.raises(access.InstallerAccessError, match="could not be confirmed"):
        context.configure(Mock(side_effect=forbidden()))
    assert context.clock.now == 0


@pytest.mark.parametrize("link", [
    "https://evil.example/roleAssignments",
    "https://management.azure.com" + COLLECTION.replace(GROUP, "other") + "?api-version=2022-04-01",
    "https://management.azure.com" + COLLECTION + "?api-version=2022-04-01&$filter=wrong",
])
def test_pagination_cannot_escape_exact_collection_and_identity_filter(context, link):
    context.arm.extra_list = {"nextLink": link}
    with pytest.raises(access.InstallerAccessError):
        context.configure(Mock(side_effect=forbidden()))
    assert not any(method == "PUT" for method, *_ in context.arm.calls)
    assert not any(url == link for _, url, _ in context.arm.calls)


@pytest.mark.parametrize("pages", [2, 6])
def test_pagination_follows_same_collection_but_stops_after_five_pages(context, pages):
    original = context.arm._send_json
    count = [0]
    item = assignment()
    context.arm.items = [item]
    def request(method, url, **kwargs):
        if method == "GET" and urlsplit(url).path == COLLECTION:
            count[0] += 1
            result = original(method, url, **kwargs)
            if count[0] < pages:
                link = url.split("&$skiptoken=")[0] + "&$skiptoken=" + str(count[0])
                return 200, {"value": [], "nextLink": link}, {}
            return result
        return original(method, url, **kwargs)
    context.arm._send_json = request
    if pages == 2:
        assert context.configure(Mock(side_effect=[forbidden(), "done"])) == "done"
    else:
        with pytest.raises(access.InstallerAccessError):
            context.configure(Mock(side_effect=forbidden()))
    assert count[0] == min(pages, 5)
    assert not any(method == "PUT" for method, *_ in context.arm.calls)


def test_deadline_bounds_total_attempts_and_no_callback_at_deadline(context):
    times, budgets = [], []

    def callback(budget):
        times.append(context.clock.now)
        budgets.append(budget)
        raise wrapped()

    with pytest.raises(access.InstallerAccessError, match="bounded access wait"):
        context.configure(callback)
    assert len(times) == 40
    assert context.clock.now == 600 and times[-1] == 585
    assert sum(context.clock.waits) == 600
    assert budgets[-1] == 15 and budgets[0] == 60
    assert max(budgets) == 60


def test_sleep_overshoot_never_submits_after_deadline(context, monkeypatch):
    monkeypatch.setattr(access.time, "sleep", lambda _: setattr(context.clock, "now", 601))
    callback = Mock(side_effect=forbidden())
    with pytest.raises(access.InstallerAccessError):
        context.configure(callback)
    assert callback.call_count == 1


def test_configuration_elapsed_time_reduces_remaining_wait_and_request_budget(context):
    budgets = []
    def callback(budget):
        budgets.append(budget)
        context.clock.now += budget
        raise forbidden()
    with pytest.raises(access.InstallerAccessError):
        context.configure(callback)
    assert len(budgets) == 9
    assert context.clock.now == 660  # initial probe precedes the 600-second propagation deadline
    assert all(budget <= 60 for budget in budgets)


@pytest.mark.parametrize("error", [forbidden(400), ServiceRequestError("transport"), KeyboardInterrupt()])
def test_retry_failure_or_cancellation_propagates_without_more_retries(context, error):
    callback = Mock(side_effect=[forbidden(), error])
    with pytest.raises(type(error)) as caught:
        context.configure(callback)
    assert caught.value is error and callback.call_count == 2


def test_cancellation_during_grant_is_not_swallowed_or_retried(context):
    original = context.arm._send_json
    def request(method, url, **kwargs):
        if method == "PUT":
            raise KeyboardInterrupt()
        return original(method, url, **kwargs)
    context.arm._send_json = request
    callback = Mock(side_effect=forbidden())
    with pytest.raises(KeyboardInterrupt):
        context.configure(callback)
    assert callback.call_count == 1 and context.arm.closed
    assert not context.clock.waits


def test_borrowed_arm_credential_closes_transport_not_sdk_identity(monkeypatch):
    credential = Mock()
    default = Mock(side_effect=AssertionError("Do not create a second identity"))
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", default)
    with AzureArmClient(credential=credential) as arm:
        arm._transport.close = Mock()
    arm._transport.close.assert_called_once()
    credential.close.assert_not_called()
    default.assert_not_called()


def test_default_arm_client_still_owns_credential(monkeypatch):
    credential = Mock()
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", lambda: credential)
    with AzureArmClient() as arm:
        arm._transport.close = Mock()
    credential.close.assert_called_once()
    arm._transport.close.assert_called_once()


@pytest.mark.parametrize("command", ["install", "deploy"])
@pytest.mark.parametrize("failure", [None, "iam", "filtered-policy", "transport", "cancel"])
def test_real_cli_sdk_orchestration_repairs_403_without_changing_tools_and_closes_once(
    context, monkeypatch, capsys, tmp_path, command, failure,
):
    from azure.ai.projects import AIProjectClient
    from azure.core.credentials import AccessToken
    from azure_bing_assistant import cli
    from test_web_policy import AgentTransport, JsonResponse

    events = []
    class Transport(AgentTransport):
        def close(self):
            events.append("project-close")

        def send(self, request, **kwargs):
            if not self.requests:
                self.requests.append(request)
                return JsonResponse(request, {"error": {"message": "PRIVATE"}}, status=403)
            if failure == "transport":
                self.requests.append(request)
                raise ServiceRequestError("PRIVATE ambiguous agent POST")
            if failure == "cancel":
                self.requests.append(request)
                raise KeyboardInterrupt()
            response = super().send(request, **kwargs)
            events.append("agent-configured")
            return response

    transport = Transport(strip_filter=failure == "filtered-policy")
    credential = context.credential
    credential.get_token.return_value = AccessToken(token(), 9999999999)
    credential.close.side_effect = lambda: events.append("credential-close")
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", lambda: credential)
    monkeypatch.setattr(
        "azure.ai.projects.AIProjectClient",
        lambda **kwargs: AIProjectClient(**kwargs, transport=transport),
    )
    if failure == "iam":
        context.arm.put_status = 403
    values = {
        "AZURE_SUBSCRIPTION_ID": SUB, "AZURE_RESOURCE_GROUP": GROUP,
        "SERVICE_WEB_NAME": "app-demo-offline", "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT,
        "MODEL_DEPLOYMENT_NAME": "offline-model", "CHATBOT_NAME": "offline-agent",
        "KNOWLEDGE_MODE": "off", "UI_LANGUAGE": "en", "WEB_GROUNDING_SITES": "example.org",
    }
    class Runner:
        def ensure_environment(self, _):
            events.append("environment")

        def run(self, argv):
            if argv[:3] == ["azd", "deploy", "web"]:
                events.append("package")
            else:
                values[argv[3]] = argv[4]

        def get_environment_values(self, _):
            return dict(values)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "AzdRunner", lambda _: Runner())
    monkeypatch.setattr(cli, "AzureProvisioner", lambda _: SimpleNamespace(run=lambda _: dict(values)))
    monkeypatch.setattr(cli, "_sync_app_service_settings", lambda *_: events.append("settings"))
    monkeypatch.setattr(cli.subprocess, "run", Mock(side_effect=AssertionError("No live commands")))
    arguments = [command, "--environment", "demo", "--ui-language", "en"]
    if command == "install":
        arguments += [
            "--non-interactive", "--mode", "off", "--subscription", SUB, "--resource-group", GROUP,
            "--location", "westeurope", "--model-name", "offline-model", "--model-version", "1",
            "--model-format", "OpenAI", "--model-sku", "GlobalStandard", "--model-capacity", "7",
            "--deployment-name", "offline-model", "--chatbot-name", "offline-agent",
            "--websites", "example.org", "--accept-bing-terms", "--foundry-user-role-id", ROLE,
        ]
    result = cli.main(arguments)
    captured = capsys.readouterr()
    assert result == (0 if failure is None else 130 if failure == "cancel" else 2)
    assert events.count("project-close") == events.count("credential-close") == 1
    assert events.index("project-close") < events.index("credential-close")
    if failure is None:
        assert events.index("agent-configured") < events.index("settings") < events.index("package")
        assert '"status": "succeeded"' in captured.out
    else:
        assert "settings" not in events and "package" not in events
        assert "PRIVATE" not in captured.err and captured.out == ""
    assert not (tmp_path / ".azure").exists()
    assert len(transport.requests) == (1 if failure == "iam" else 2)
    expected_tools = [{"type": "web_search", "filters": {"allowed_domains": ["example.org"]}}]
    for request in transport.requests:
        assert json.loads(request.body)["definition"]["tools"] == expected_tools
    if command == "install" and failure is not None:
        assert "Safe recovery:" in captured.err
