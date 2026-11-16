"""Provider-specific rules that keep an agent to the mailboxes and numbers assigned to it.

Assignment alone only decides whether a provider's tools are mounted (agent_service_store). These rules
look inside a call. They are written against the tool definitions AgentMail reported on a live account
(2026-11-16): every inbox-scoped tool has a required `inboxId`, and the inbox id is the email address.
A provider without a rule here is not narrowed by argument; the owner still sees every argument on the
approval card.
"""

import json

# Providers whose tools name the inbox in an `inboxId` argument.
_INBOX_ID_PROVIDERS = {"agentmail"}
_LIST_TOOLS = {"list_inboxes"}


def _has_inbox_id(input_schema: dict) -> bool:
    properties = (input_schema or {}).get("properties")
    return isinstance(properties, dict) and "inboxId" in properties


def refusal(provider: str, input_schema: dict, arguments: dict, assigned: list[str]) -> str | None:
    """A reason code when the call names an inbox that is not assigned to the agent, else None."""
    if provider not in _INBOX_ID_PROVIDERS or not _has_inbox_id(input_schema):
        return None
    value = arguments.get("inboxId") if isinstance(arguments, dict) else None
    if not isinstance(value, str) or value.strip().lower() not in {address.lower() for address in assigned}:
        return "resource_not_assigned"
    return None


def narrows_result(provider: str, tool_name: str) -> bool:
    return provider in _INBOX_ID_PROVIDERS and tool_name in _LIST_TOOLS


def _only_assigned(data: dict, allowed: set[str]) -> dict:
    inboxes = [inbox for inbox in data["inboxes"]
               if isinstance(inbox, dict) and str(inbox.get("inboxId", "")).lower() in allowed]
    return {**data, "inboxes": inboxes, "count": len(inboxes)}


def narrow_result(result: dict, assigned: list[str]) -> dict:
    """The tool result with only the assigned inboxes left in it. Fails closed: a result that cannot be
    read as an inbox list is replaced by an error rather than passed through."""
    if result.get("isError") or result.get("error"):
        return result
    allowed = {address.lower() for address in assigned}
    data = result.get("structuredContent")
    if not (isinstance(data, dict) and isinstance(data.get("inboxes"), list)):
        data = None
        for block in result.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                try:
                    parsed = json.loads(block.get("text", ""))
                except ValueError:
                    continue
                if isinstance(parsed, dict) and isinstance(parsed.get("inboxes"), list):
                    data = parsed
                    break
    if data is None:
        return {"error": "The inbox list could not be limited to this agent's inboxes, so it was withheld.",
                "code": "result_not_filterable"}
    kept = _only_assigned(data, allowed)
    return {"content": [{"type": "text", "text": json.dumps(kept)}], "structuredContent": kept, "isError": False}
