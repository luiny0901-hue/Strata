# IQ4_XS vision CPU/GPU comparison

Measured on 2026-10-17 on Windows with the existing NVFP4 fork + Unsloth UD-IQ4_XS profile. This is a direct local API benchmark, not an OpenCode end-to-end coding-task run.

## Configuration

- Engine: RTX 3090 Ti, GPU 1 only; 1,280 MiB reserve; 262,144-token context ceiling.
- CPU/RAM: AMD Ryzen Threadripper 3970X, 32 cores / 64 threads; 128 GiB RAM.
- Driver: NVIDIA 616.92. The RTX 3090 was not selected for inference.
- Vision input: 1920x1080 image, 1,024 image-token maximum.
- Workload: same synthetic 20,598-token C# review prompt and 192-token output cap; one warm-up and three measured calls per condition.
- The CPU/GPU profile pair changed only `vision.gpu` and the log path. The ON/OFF profiles changed only the uncensored switch and log path. The fork maps that switch to `experimental_speed_projection`; do not interpret ON/OFF rate differences as a clean vision-placement comparison.
- All 12 measured requests returned HTTP 200 with 20,598 prompt tokens, 192 generated tokens and 0 cached prompt tokens.

## Results

| Mode | Vision | Prefill median (range) tok/s | Decode median (range) tok/s | Client-observed request wall median |
| --- | --- | ---: | ---: | ---: |
| OFF | CPU | 3,112.1 (3,107.6–3,118.8) | 104.2 (98.1–119.8) | 16.500 s |
| OFF | GPU | 3,117.9 (3,100.0–3,123.1) | 100.6 (97.2–103.2) | 16.534 s |
| ON | CPU | 3,082.3 (3,070.7–3,106.0) | 116.4 (102.5–118.7) | 16.391 s |
| ON | GPU | 3,062.2 (2,953.2–3,075.9) | 110.3 (108.2–113.6) | 16.592 s |

GPU vs CPU within each mode: OFF prefill +0.19%, decode -3.45%, wall +0.21%; ON prefill -0.65%, decode -5.24%, wall +1.23%. These small differences are within a three-run comparison and do not show a practical GPU-vision speedup. Speculative draft acceptance varied between calls.

GPU vision started successfully, but the engine used about 21.8 GiB (22.3 GB) of 24 GiB VRAM during requests, leaving about 1.9 GiB. CPU vision remains the default for both launchers because moving the encoder to GPU showed no material benefit in this workload and competes for the same GPU memory.

## Evidence and limits

- [`receipt.json`](receipt.json): host, settings, fixture hashes, run method and scope.
- [`benchmark.py`](benchmark.py): request generator and measurement harness.
- [`verification.txt`](verification.txt): local setup unit tests (12/12) and Python syntax check.
- [`off-cpu.json`](off-cpu.json), [`off-gpu.json`](off-gpu.json), [`on-cpu.json`](on-cpu.json), [`on-gpu.json`](on-gpu.json): warm-up and per-request API measurements.
- Image fixture bytes are not committed because the screenshot contains source-like text from a separate local project. The receipt keeps SHA-256 hashes; reproducing the exact visual input requires the original local fixture.
- The API does not expose isolated image-encoder timing. Client wall time minus server prefill/decode time is a residual that includes image encoding and other request/server/network overhead, not a direct encoder measurement.
- This does not test visual answer correctness, full 262K context, OpenCode tool use, or repeated production workloads. Each cell has only three measured calls.
- The standard IQ4_XS setup unit suite separately verifies both rendered profiles use CPU vision by default.
