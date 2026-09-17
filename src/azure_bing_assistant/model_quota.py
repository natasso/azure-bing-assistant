"""Read-only subscription/region quota, joined by Azure's ModelSku.usageName.

Schema: Microsoft.CognitiveServices stable/2024-10-01, Usages_List and
ModelSku in Azure/azure-rest-api-specs. Usage.unit is extensible and does not
define a conversion to deployment capacity or model-specific TPM/RPM.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import math
from time import monotonic
from typing import Any, Callable, Sequence
from urllib.parse import parse_qs, quote, urlsplit


API_VERSION = "2024-10-01"
MAX_PAGES = 20
MAX_ROWS = 10000
ARM_HOSTS = {
    "management.azure.com",
    "management.usgovcloudapi.net",
    "management.chinacloudapi.cn",
    "management.microsoftazure.de",
}


class QuotaUnavailable(RuntimeError):
    """The API did not provide an unambiguous, complete quota snapshot."""


@dataclass(frozen=True)
class ModelQuota:
    usage_name: str
    limit: Decimal
    current: Decimal
    unit: str
    checked_at: datetime
    period: str | None = None
    status: str | None = None

    @property
    def remaining(self) -> Decimal:
        return max(Decimal(0), self.limit - self.current)


def metadata_text(value: Any, maximum: int = 512) -> str | None:
    if (
        isinstance(value, str)
        and 0 < len(value) <= maximum
        and value == value.strip()
        and all(character.isprintable() for character in value)
    ):
        return value
    return None


def _number(value: Any) -> Decimal:
    if type(value) not in (int, float) or value < 0:
        raise QuotaUnavailable()
    if isinstance(value, float) and not math.isfinite(value):
        raise QuotaUnavailable()
    return Decimal(str(value))


def _page_url(value: Any, path: str) -> str:
    if metadata_text(value, 8192) is None:
        raise QuotaUnavailable()
    try:
        parsed = urlsplit(value)
        if (
            parsed.fragment
            or (parsed.scheme and parsed.scheme != "https")
            or (parsed.netloc and parsed.netloc.casefold() not in ARM_HOSTS)
            or (parsed.scheme and not parsed.netloc)
            or parsed.path.casefold() != path.casefold()
            or parse_qs(parsed.query).get("api-version") != [API_VERSION]
        ):
            raise QuotaUnavailable()
    except ValueError as exc:
        raise QuotaUnavailable() from exc
    # Keep every page on az rest's configured ARM cloud and the original scope.
    return f"{path}?{parsed.query}"


def read_model_quota(
    read_json: Callable[[Sequence[str]], Any],
    subscription_id: str,
    location: str,
    usage_name: str,
) -> ModelQuota:
    path = (
        f"/subscriptions/{quote(subscription_id, safe='')}/providers/"
        f"Microsoft.CognitiveServices/locations/{quote(location, safe='')}/usages"
    )
    url = f"{path}?api-version={API_VERSION}"
    visited: set[str] = set()
    result: tuple[Decimal, Decimal, str, str | None, str | None] | None = None
    row_count = 0
    deadline = monotonic() + 60
    if metadata_text(usage_name) is None:
        raise QuotaUnavailable()
    for _ in range(MAX_PAGES):
        if url in visited or monotonic() >= deadline:
            raise QuotaUnavailable()
        visited.add(url)
        payload = read_json([
            "az", "rest", "--method", "get", "--subscription", subscription_id,
            "--url", url, "--output", "json",
        ])
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise QuotaUnavailable()
        row_count += len(payload["value"])
        if row_count > MAX_ROWS:
            raise QuotaUnavailable()
        for row in payload["value"]:
            if not isinstance(row, dict) or not isinstance(row.get("name"), dict):
                raise QuotaUnavailable()
            name = metadata_text(row["name"].get("value"))
            if name is None:
                raise QuotaUnavailable()
            if name.casefold() != usage_name.casefold():
                continue
            unit = metadata_text(row.get("unit"), 128)
            period = row.get("quotaPeriod")
            status = row.get("status")
            if (
                unit is None
                or (period is not None and metadata_text(period) is None)
                or (status is not None and metadata_text(status) is None)
            ):
                raise QuotaUnavailable()
            candidate = (
                _number(row.get("limit")), _number(row.get("currentValue")),
                unit, period, status,
            )
            if result is not None and result != candidate:
                raise QuotaUnavailable()
            result = candidate
        next_link = payload.get("nextLink")
        if next_link in (None, ""):
            if result is None:
                raise QuotaUnavailable()
            limit, current, unit, period, status = result
            return ModelQuota(
                usage_name, limit, current, unit, datetime.now(timezone.utc), period, status,
            )
        url = _page_url(next_link, path)
    raise QuotaUnavailable()
