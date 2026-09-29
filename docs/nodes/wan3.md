# MATRIX WAN 3.0

`MATRIX_Wan3` submits WAN 3.0 jobs through a user-owned WaveSpeed account and
returns the downloaded result as a native ComfyUI `VIDEO`. Every new generation is
billable. Review the estimated route and settings before queueing; estimates are
dated guidance, not a live provider quote.

## Operations and catalog routes

The node exposes five operations: Text to Video, Image to Video, Reference to
Video, Edit Video, and Extend Video. Standard and Prime select the provider tier;
Image to Video also exposes Regular and Spicy variants. Those combinations map to
twelve catalog routes. Unsupported combinations fail before media encoding,
upload, or submission.

Dynamic sockets preserve native ComfyUI media. Image routes accept first and last
frames. Reference routes accept up to ten images, five videos, and five audio
clips. Edit and Extend require their operation-specific inputs. Native VIDEO
materialization and provider trimming remain explicit opt-ins.

## Credentials and billing

Bring your own WaveSpeed API key. The key is stored outside workflows under the
ComfyUI user-data directory `matrix-wan3/credentials/`, protected with Windows
DPAPI or owner-only POSIX storage. Workflows serialize only a non-secret credential
scope. The local same-origin routes are:

- `GET /matrix-wan3/credentials/v1/status`
- `POST /matrix-wan3/credentials/v1/set`
- `POST /matrix-wan3/credentials/v1/disconnect`
- `POST /matrix-wan3/credentials/v1/verify`

The verify operation checks account access but does not generate media. Old Demo
workflows remain billing-blocked until deliberately activated from the current UI.
The runner never automatically retries a paid submission.

## Recovery and local data

Single-submit recovery uses SQLite WAL journals under the ComfyUI user-data path
`matrix-wan3/`, including `tasks.sqlite3`, `uploads.sqlite3`, `results/`, and lock
files. Uploaded assets are cached by account and content for up to six days. An
uncertain submission is recovered or surfaced for review instead of blindly
resubmitted. Updates and rollbacks must preserve this directory.

## Host boundary and limits

This node requires ComfyUI 0.37.0 or newer, frontend 1.53.6 or newer, Python 3.10
or newer, and PyAV provided by the ComfyUI host. The pack does not install PyAV or
replace Torch, CUDA, or the host media stack. Provider limits, route availability,
pricing, and accepted media can change; current local validation remains the final
pre-submit gate.

Offline verification covers catalog validation, credential protection and routes,
identity, journals, upload caching, bounded TLS transport, media preparation,
workflow ABI, frontend migration, shared HALO housing, and fake-transport request
paths with network disabled. It does not prove a paid provider generation, visual
quality, provider uptime, or current pricing. Classic and Nodes 2.0 evidence is
scoped to MATRIX WAN 3.0 (and separately documented H3 controls), not the whole pack.

## Update and rollback

Do not enable this pack beside a standalone `MATRIX_Wan3` installation: both would
register the same class ID and credential routes. Stop ComfyUI, preserve workflows
and `matrix-wan3/` user data, install into a clean folder, and verify the exact
manifest before disabling the previous version recoverably. See
[INSTALL.md](../../INSTALL.md), [compatibility](../compatibility.md),
[security](../../SECURITY.md), and the [Apache 2.0 license](../../LICENSE).
