"""Safe operator guidance for the optional document-ingestion path."""

from __future__ import annotations

import re


_STORAGE = re.compile(r"^[a-z0-9]{3,24}$")
_CONTAINER = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")
_RESOURCE_GROUP = re.compile(r"^[A-Za-z0-9._()\-]{1,90}$")


def document_upload_guidance(
    resource_group_name: str,
    account_name: str,
    container_name: str,
) -> str:
    if not _RESOURCE_GROUP.fullmatch(resource_group_name):
        raise ValueError("resource group name is invalid")
    if not _STORAGE.fullmatch(account_name):
        raise ValueError("storage account name is invalid")
    if not _CONTAINER.fullmatch(container_name):
        raise ValueError("container name is invalid")
    return "\n".join(
        [
            "Document ingestion destination:",
            (
                f"Azure portal > Resource groups > {resource_group_name} > "
                f"Storage accounts > {account_name} > Data storage > Containers > {container_name}"
            ),
            "Managed-identity/RBAC upload (run after az login as Storage Blob Data Contributor):",
            (
                "az storage blob upload-batch "
                f"--account-name {account_name} --destination {container_name} "
                "--source <local-folder> --auth-mode login"
            ),
            "The chat application has no upload endpoint.",
        ]
    )
