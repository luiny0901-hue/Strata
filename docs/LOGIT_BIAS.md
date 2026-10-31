# Per-request token biases

`POST /v1/chat/completions` accepts `logit_bias` with a supporting CUDA or HIP
engine, without continuous batching. The same bias applies to every generated
token in the request, including tokens checked together during speculative
decoding. It does not force single-token verification windows.

## Example: Hello becomes Hi

We use `Hello` because it is a familiar word, it is exactly one token in the
tested tokenizer, and the unbiased model naturally chooses it for this prompt.
The tokenizer maps `Hello` to **token ID 9419**. That number identifies the token;
it is not its logit or probability. The value **-100** is the requested bias,
which this implementation treats as a hard exclusion.

Before: send this request without a bias. The measured response was **Hello**.

```json
{
  "model": "bias-validation",
  "messages": [{"role": "user", "content": "Reply with one English greeting, one word only."}],
  "max_tokens": 8,
  "temperature": 0,
  "reasoning_effort": "none"
}
```

After: add only `logit_bias`. The measured response was **Hi** (token 12675).

```json
{
  "model": "bias-validation",
  "messages": [{"role": "user", "content": "Reply with one English greeting, one word only."}],
  "max_tokens": 8,
  "temperature": 0,
  "reasoning_effort": "none",
  "logit_bias": {"9419": -100}
}
```

The equivalent llama.cpp-style pair list is `"logit_bias": [[9419, false]]`;
it also produced **Hi**. Removing the field on the next request restored **Hello**.
Nothing is banned by default. This is a per-request example, not a built-in list.
The `model` value above is the test server's alias; use your server's model name.
Numeric pair values are also supported, for example `[[42, 2.5]]`.
Token IDs belong to the loaded model's tokenizer; the example ID is not portable
between arbitrary models. Leading spaces and letter case can also change token IDs.
The four English requests were measured on ISTA IQ3_XXS; a
[reproduction script](../tools/logit_bias_english_example.py) is included.

## Semantics and limits

Biases must be finite numbers in `[-100, 100]`. Negative values discourage a
token, positive values encourage it, and **-100 excludes it** (`false` in a
pair list has the same meaning). The bias is added before repetition/frequency/
presence penalties, temperature, and candidate filtering. Raw model logits
are not overwritten. Banning a token does not ban a word or language: other
token sequences may produce the same text.

Omitting the field, `null`, `{}`, or `[]` clears the previous request's bias.
Biases are request sampling state; they are not stored in a conversation cache.
They do not change the model weights or prompt KV. A fixed dense vocabulary
vector is uploaded when the bias changes and reused within the request.

Malformed entries, duplicate IDs in pair lists, IDs outside the vocabulary,
out-of-range biases, or banning the entire vocabulary return HTTP 400. Validation
on the chat route occurs before SSE streaming headers are sent. Nonempty biases
also return HTTP 400 with older engines, the current SYCL engine, or continuous
batching (`--batch`), rather than being silently ignored. The engine advertises
`logit_bias=1` in its `INFO` response when this implementation is present.

MTP target verification applies the bias; the draft model is not biased, so a
restrictive list may reduce draft acceptance. Ordinary MTP was tested. The
experimental coupled/rejection-sampling combinations and multi-GPU execution
were not validated in this campaign. There is no startup bias-file option in
this change: send the field with each request.

## Server-side default ban: `ban_cjk_tokens`

For a deployment whose output language never contains Han characters (a Korean
assistant, for example), the server can ban every token whose decoded surface
contains a Han character for every request, instead of each client sending the
list. The map is built once at server startup from the server's own tokenizer
(`serve/cjk_ban.py`) and rides the run config's sampling block, which every
route merges as its defaults - so one request can still override the ban with
its own `logit_bias`, and an explicit `{}` clears it for that request. The run
config turns it on with `"ban_cjk_tokens": true` (default off; this checkout
enables it in the UD-IQ4_XS ON profile template, and
`tools/patch_nvfp4_cjk_ban.py` installs the hook into the NVFP4 fork's server
at launch like the other patch scripts).

A token exclusion is complete for token surfaces - a token can only emit what
its surface holds - but a byte-level tokenizer can still spell a Han character
out of byte tokens, which this model does for these characters about never.
Banning is model-wide, not language-aware: a Chinese answer on such a profile
must send its own bias list.

Measured 2026-10-31 on this PC (CPU only, the UD-IQ4_XS pack tokenizer): the
ban covers **55,328 of 248,320 tokens** (22.3%), is built in **0.49 s** at
startup, and makes the engine's per-request command line carry a 660 KB bias
string. Because the same map object arrives on every request,
`serve/logit_bias.py` now remembers the normalized map and the engine key per
object identity: for this ban the first `engine_key` call took **111 ms** and
a repeated one **0.01 ms**; `normalize` went from **88 ms** to **0.9 ms**.
Large maps therefore count as read-only; never edit a passed-in map in place.
End-to-end decode speed with the ban active on the live server has not been
measured yet, and the MTP note above applies to the ban list too.
