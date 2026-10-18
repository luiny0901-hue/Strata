# 262K OpenCode coding-task comparison: IQ4_XS selection evidence

Date: 2026-10-17. Windows, RTX 3090 Ti GPU 1, 128 GiB RAM. OpenCode 2.0.22.
All configurations declared a 262,144 context ceiling; the observed task prompts
were 41,507-46,729 tokens. This was not a full 262K context stress test.

## Results

| Runtime + model | Elapsed | Max observed prompt | Largest fresh prefill | Longest generation | Weighted decode | Tool calls | Independent CPU tests |
|---|---:|---:|---:|---:|---:|---:|---:|
| Standard Strata + Unsloth UD-IQ4_XS | 216.4 s | 46,418 | 20,050 / 7.814 s = 2,565.8 tok/s | 8,193 / 83.479 s = 98.1 tok/s | 102.3 tok/s | 17 | 25/25 |
| NVFP4 fork + Unsloth UD-IQ4_XS | 165.3 s | 41,507 | 19,971 / 6.314 s = 3,162.8 tok/s | 8,193 / 77.389 s = 105.9 tok/s | 109.3 tok/s | 12 | 31/31 |
| NVFP4 fork + dedicated NVFP4 GPTQ | 233.5 s | 46,729 | 17,723 / 6.370 s = 2,782.4 tok/s | 8,192 / 92.036 s = 89.0 tok/s | 89.2 tok/s | 23 | 28/28 |
| NVFP4 fork + Unsloth UD-Q4_K_XL, historical separate run | 246.8 s | 46,643 | 17,686 / 7.046 s = 2,510.2 tok/s | 8,193 / 98.458 s = 83.2 tok/s | 82.9 tok/s | 15 | 31/31 |

The IQ4_XS fork run was fastest in this single coding task. This does not
establish a general ranking: each model produced different output lengths and
tool-call counts, runs were not repeated or averaged, and request bodies were
not byte-identical. The three IQ4_XS/GPTQ rows are summarized from the same
comparison run; Q4_K_XL is documented in the separate historical report.

## What was tested

- The same save/continue coding task ran in disposable project copies; the
  original workspace was preserved. Raw task prompts and the project source
  are not included in this repository.
- Each model run completed with exit code 0. The independent Node tests were
  run after the agent task: standard IQ4_XS 25/25, NVFP4 fork + IQ4_XS 31/31,
  dedicated NVFP4 GPTQ 28/28. The three sanitized test outputs are committed
  beside this report.
- The test is a DOM/localStorage stub CPU simulation. Browser rendering and
  visual correctness were not tested.
- The server vision path was enabled with CPU encoding, but no image was sent.
  This is not a vision test or vision speed result.
- UD-IQ4_XS uses IQ4_XS weights under the NVFP4 fork; this is not the dedicated
  NVFP4 GPTQ model.

The fork + IQ4_XS setting used int8 KV, MTP spec 4/min-p 0.5, auto expert
cache, auto prefill, a 32,768-token resident KV window, and a 1,280 MiB VRAM
reserve. The task's OpenCode ceiling was 32,000 output tokens. These settings
are reproduced in the current setup templates. The current uncensored ON/OFF
profiles additionally load the fork control vector; that vector was not part
of the scored IQ4_XS run, and its output-quality effect on UD-IQ4_XS is
unverified.

## Limits and retained attempt history

- The 262K limit was configured, but the largest observed prompt was 46,729
  tokens. Full 262K behavior is unverified on this 24 GB GPU.
- About 500 tok/s appeared on small incremental prefill samples after KV
  reuse; the largest fresh chunks measured about 2.5K-3.2K tok/s. These are
  different workloads, not contradictory universal rates.
- Two preliminary GPTQ starts with 55 and 64 GiB RAM budgets warned that zero
  prompt-lent experts had RAM copies; they were stopped before scoring. The
  scored GPTQ run used the full RAM resident arena.
- An earlier standard Strata Ctrl+C shutdown printed `strata stopped` but
  Python returned exit 1 after an ignored finalizer `OSError [Errno 22]`.
  The process, listener, and GPU memory were confirmed clear afterward. This
  warning is retained, not counted as a passing test.
- Raw per-request Strata and OpenCode logs are not committed because they
  include prompts and user workspace details. This report and the independent
  test output files are the shareable evidence.

## Vision CPU/GPU follow-up

A separate same-day 1920x1080 image benchmark compared CPU and GPU vision placement for both uncensored modes. It found no material prefill, decode, or request-wall improvement from GPU vision; see the [follow-up results and per-run evidence](2026-10-17-iq4xs-vision-cpu-gpu/README.md). This separate test does not change the historical no-image result above.
