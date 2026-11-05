"""Organization-wide cloud usage: reserve before dispatch, settle on complete usage."""


def reported_total(result):
    """Missing/partial usage must never turn an uncertain cloud charge into zero."""
    usage = result.get("usage") if isinstance(result, dict) else None
    if not isinstance(usage, dict):
        return None
    prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if type(prompt) is not int or type(completion) is not int:
        return None
    if prompt < 0 or completion < 0:
        return None
    total = prompt + completion
    if total > 2147483647:
        return None
    if "total_tokens" in usage and (type(usage["total_tokens"]) is not int or usage["total_tokens"] != total):
        return None
    return total


def reserve_total(parameters, settings):
    context = parameters.get("_patient_context")
    if context:
        budget = context["budget"]["conversation"]
        return budget["prompt_tokens"] + budget["reserved_output_tokens"] + budget["safety_margin_tokens"]
    # The same conservative UTF-8 estimate used by remote patient prompt fitting.
    return (
        sum(len(message["content"].encode("utf-8")) + 32 for message in parameters["messages"])
        + 64
        + parameters["max_tokens"]
    )
