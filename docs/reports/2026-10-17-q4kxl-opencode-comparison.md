# OpenCode coding-task comparison: NVFP4 fork and Q4_K_XL

Measured on 2026-10-17 on Windows with an RTX 3090 Ti (GPU 1), 128 GiB RAM,
NVFP4 fork 0.1.44.1-nvfp4.2, and OpenCode 2.0.22. The task was a
save-and-continue coding change in isolated copies; each run used the same
task input. These are individual agent runs, not repeated benchmark averages.

## Results

| Runtime + model | OpenCode elapsed | Largest observed prompt | Largest fresh prefill sample | Longest generation | Weighted decode | Tool calls | Independent CPU test |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Standard Strata + UD-IQ4_XS | 216.4 s | 46,418 | 20,050 / 7.814 s = 2,565.8 tok/s | 8,193 / 83.479 s = 98.1 tok/s | 102.3 tok/s | 17 | 25/25 |
| NVFP4 fork + UD-IQ4_XS | 165.3 s | 41,507 | 19,971 / 6.314 s = 3,162.8 tok/s | 8,193 / 77.389 s = 105.9 tok/s | 109.3 tok/s | 12 | 31/31 |
| NVFP4 fork + dedicated NVFP4 GPTQ | 233.5 s | 46,729 | 17,723 / 6.370 s = 2,782.4 tok/s | 8,192 / 92.036 s = 89.0 tok/s | 89.2 tok/s | 23 | 28/28 |
| NVFP4 fork + Unsloth UD-Q4_K_XL | 246.8 s | 46,643 | 17,686 / 7.046 s = 2,510.2 tok/s | 8,193 / 98.458 s = 83.2 tok/s | 82.9 tok/s | 15 | 31/31 |

The Q4_K_XL run loaded with a configured context ceiling of 262,144 and
completed its coding task. Its largest prompt was 46,643 tokens, so this does
not prove full 262K context behavior. The independent test was a DOM and
localStorage CPU stub; browser rendering and image input were not tested.

The Q4_K_XL run had lower weighted decode than the IQ4_XS and GPTQ runs in this
single sample. Task latency, output lengths, prompt sizes, and tool-call counts
differed, so the table is directional evidence rather than a general ranking.
The vision encoder was configured for CPU use, but no image was sent. An
incremental prefill reading near 500 tok/s measured a small number of fresh
tokens after KV reuse; it is not comparable to the larger cold-prefill samples
in the table. The scored Q4_K_XL run used uncensored=false without loading the
refusal projection. The new ON/OFF profiles include the projection and have
only passed configuration parsing; their live generation modes were not run.

## Q4_K_XL preparation and launch settings

- Model: official unsloth/Qwen3.8-Flash-Next-GGUF, revision
  766911a6b7369840a91dbcd95f9f997acaab6cd6, UD-Q4_K_XL, four shards
  totaling 111,334,654,784 bytes.
- Pack: made with Strata tools/iq_pack.py --compat-bf16; 1,079 tensors,
  303 served natively, 460 conversions (264 exact and 196 rounded), maximum
  reported absolute error 0.0144; 1.38 GiB arena and no separate experts.bin.
- GPU: RTX 3090 Ti only; int8 KV; 32,768 resident KV; MTP 6 / min-p 0.7;
  automatic expert cache and prefill; 1,280 MiB VRAM reserve; CPU vision
  encoding; STRATA_HC_Q8=1; STRATA_ROUTE_TAIL_SKIP=0.
- The fork loaded 71.73 GiB of experts into RAM and a 14.53 GiB GPU expert
  cache. Its API reported loaded=true, context 262144, and images enabled.
- The fork's published profile for one 24 GB GPU recommends 131,072 context.
  The measured 262K ceiling is an experimental over-spec for this card.

## Attempt and cleanup notes

- An initial pack attempt with the fork's .venv-model stopped because NumPy
  was absent. The pack was then produced with the already-installed Strata
  .venv; no dependency was installed.
- Two preliminary GPTQ launches using 55 GiB and 64 GiB RAM budgets reported
  zero RAM-resident copies of prompt-lent experts. Those attempts were stopped
  before comparison; the scored GPTQ run used the full resident RAM arena.
- One graceful server shutdown printed [strata] stopped but Python returned
  exit 1 after an ignored finalizer OSError [Errno 22]. Process, listener,
  and GPU checks confirmed the server exited and RTX 3090 Ti memory returned
  to 0 MiB. This warning is retained; it is not described as a clean process
  exit.

The actual task source, generated project files, prompts, OpenCode event logs,
and full Strata logs are intentionally not included. The results and settings
above are the shareable summary; model and pack SHA-256 values are in the
adjacent artifact manifest. A compact machine-readable test receipt is in
2026-10-17-q4kxl-test-receipt.json; the independent DOM-stub output is in
2026-10-17-q4kxl-independent-test.txt.
