# CUA vision detail setting — 2026-10-17

## Applied defaults

- The user-level CUA Driver config currently reads `max_image_dimension: 1920`. This setting is outside the repository and applies to both launch modes.
- Both Unsloth UD-IQ4_XS NVFP4 launchers pass `--image-max-tokens 1024` to the fork's `serve.server` process.
- Image minimum remains the fork default of 8. Forcing a minimum of 1024 did not improve the recorded sample.
- The launcher changes keep uncensored ON and OFF as separate profiles. The focused profile tests verify those mode values and the 262144 context setting.

## Measurement

A synthetic IDE screenshot was sent through isolated scratch profiles using the NVFP4 fork and Unsloth UD-IQ4_XS. The existing OpenCode endpoint was not changed; the check did not exercise a live Rider/OpenCode/CUA capture session.
All 20 scratch API requests returned HTTP 200; none were skipped or retried.

| Input image cap | Image token cap | Exact answers | Average prompt tokens | Warm request time |
|---:|---:|---:|---:|---:|
| 1568 px | 300 | 2/4 | 375 | about 1.1–1.4 s |
| 1920 px | 1024 | 4/4 | 1107 | about 2.4–2.9 s |

The four checks covered the editor filename, a source line, an issue label, and three test counts. This is one synthetic screenshot, so it is evidence for this sample only, not a general accuracy guarantee. The higher token cap added about 732 prompt tokens and was slower in these warm samples. One candidate-only uncensored ON check at 1920/1024 scored 3/4; there was no matched ON baseline.

## Verification boundary

- The CUA Driver configuration was read back as 1920 on this PC; that user-level file is not committed.
- The fork's `python -m serve.server --help` lists `--image-max-tokens`; the ordinary Strata server outside the fork does not. The BAT changes directory into the fork before importing `serve.server`.
- Launcher SHA-256: OFF `7e0f53ed3760882da6ececdcc0b28f12ff349d1a4236f7b937a84558cf695c7b`; ON `bfcec562b877e39e05b80148fdcea2f9685fdbbacd73905588c93c8da9fbca57`.
- No full model run, real Rider/OpenCode session, or CUA screen-capture workflow was repeated for this commit.
- No model, fork binary, GPU setting, OpenCode global configuration, or operational Strata service was changed.
