# Pitfalls

Non-obvious behaviour that costs time when you hit it unprepared.

## An async step shows no duration

`AllureLifecycle` keeps the current step in one global `OrderedDict` — no contextvar, no thread-local. A step held open across `await` would therefore collect attachments from whatever coroutine finished in the meantime, so with `asyncio.gather` responses end up under each other's steps.

The async decorator works around this by opening the step only after the response has arrived. The step, its title and both attachments are correct; the price is that the step's duration is meaningless and is not shown. The sync decorator has no such problem and does wrap the exchange, duration included.

## A `send` step closes before your assertions run

For `send` (and the `get`/`post`/... shortcuts) the step covers the exchange only. Everything the caller does afterwards is outside it:

```python
response = client.get("/orders/42")
response.raise_for_status()  # fails the test, but the step stays green
```

Streaming is the opposite: the caller's body runs inside the step, so a failure there marks the step failed.

```python
with client.stream("GET", "/orders") as response:
    response.raise_for_status()  # step is marked failed
```

## Streamed bodies are placeholders

A streamed response body is attached as `<streamed content>` unless the calling code read it inside the `with` block. A streamed upload body is never read at all — reading it would consume the stream and the request would then fail with `StreamClosed`. Same for the curl attachment: the body there is the placeholder, and for a JSON content type it is a JSON-valid `"<streamed content>"` string.

This is by design, not a bug to fix. If a test needs the body in the report, read it inside the block.

## An empty response body produces no content attachment

`204 No Content` and friends give a step with `Request details` and `Response headers: status = 204 [No Content]`, but no `Response content`. Do not assert "three attachments per step" as a general rule.

## A truncated attachment stops being JSON

With `max_attach_length` set, an over-long attachment is cut and its type is downgraded to plain text — Allure cannot render half a JSON document. Tests that parse `Response content` as JSON will start failing the moment a payload crosses the limit.

## Redirects: the step describes the original request

With `with_follow_redirects()`, the step title and `Request details` show the request the caller built — original method, URL and body. The response attachment describes the final response, including its status code. Intermediate hops are not in the report.

## Report failures are swallowed on purpose

If masking or serialization throws, the attachment is replaced by a short `<Ошибка формирования вложения: ClassName>` text and the call returns normally. A request that already reached the server must not surface as a network error just because the report could not be drawn — the caller might retry a non-idempotent operation.

Consequence: a weird attachment is a reporting bug, never evidence that the request failed. Only the exception class is recorded — its message could drag body fragments or a URL into the report.

## Both options at once give doubled steps

`wrap_requests_in_steps` and `wrap_requests_and_responses_in_steps` each append their own pair of decorators. Passing both produces two nested steps per request with duplicate attachments. Pick one.

## `client.client.send(...)` never reaches the report

The decorators live on `send` and `stream_request` of `http_client`. Calling straight into `httpx` skips them — the request happens and the report stays empty.

## Repeated query keys survive as lists

`?tag=new&tag=sale` is attached as `"tag": ["new", "sale"]` and rendered back into the step title as `tag=new&tag=sale`. Do not expect a flat `dict(request.url.params)` shape when asserting on the attachment.

## False alarms when reading the code

- `StepSettings` is exported from the package but you never build it yourself — the options assemble it from their parameters. It is public only so type annotations can name it.
- Options register decorators through the public `add_send_decorator` / `add_stream_decorator` methods
  during client construction. Custom options use the same extension points.
- `reader._is_loaded` checks `hasattr(message, "_content")` — the only way httpx exposes "the body is already in memory". It is a deliberate dependency on a private attribute, not an oversight.
- `_attach_safely` catches bare `Exception`, and the decorators catch `BaseException`. Both are intentional: the first keeps reporting failures away from the caller, the second makes sure a cancelled or timed-out request still leaves a step behind.
