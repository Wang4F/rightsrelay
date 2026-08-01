# RightsRelay

**Revoke once, regenerate every affected synthetic-voice derivative.**

RightsRelay is a small production-minded demo for the 2026 Backblaze Generative
Media Hackathon. A media team creates a voiceover from a source script, records
which synthetic voice profile was used, and keeps a verifiable Genblaze manifest.
If a voice profile becomes unavailable or its operational use window changes,
RightsRelay finds affected campaigns and regenerates them with an approved
replacement while preserving the old revision and hash chain.

This is operational rights tooling, not a legal-compliance engine. A status in
RightsRelay records a team's workflow decision; it does not determine whether a
license, consent, or contract is legally valid.

## Why it exists

Synthetic media is usually stored as disconnected output files. A producer may
know that a voice can no longer be used, but still lack a reliable answer to:

- Which current campaign files depend on that voice?
- What replaced each affected derivative?
- Can a reviewer verify that the replacement bytes match the recorded run?
- Are source scripts and regenerated media durably stored rather than tied to a
  provider's expiring URL?

RightsRelay makes those relationships explicit and mechanically verifiable.

## Real pipeline

1. The source script is hashed and ingested with `Pipeline.ingest`.
2. A custom `PiperTTSProvider(SyncProvider)` runs a local neural TTS model.
3. Genblaze binds the script input, voice profile, operational metadata, WAV
   hash, and replacement lineage into a canonical manifest.
4. In B2 mode, `ObjectStorageSink` uploads source and derivative assets with
   content-addressable keys, then stores the manifest.
5. Revoking a profile queries the reverse index and reruns every affected
   campaign with its designated replacement profile.

The demo uses Piper `en_US-libritts_r-medium`, a 904-speaker, 22.05 kHz model
fine-tuned from English lessac medium on LibriTTS-R `train-clean-360`. The
official model card identifies the dataset license as
[CC BY 4.0](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/libritts_r/medium/MODEL_CARD).
Piper TTS is used locally; no text or media is sent to a hosted model API.

## Run locally

Python 3.11 is recommended.

```powershell
uv venv --python 3.11 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.venv\Scripts\python.exe scripts\download_voice.py
$env:RIGHTSRELAY_VOICE_MODEL_PATH="$PWD\.models\en_US-libritts_r-medium.onnx"
$env:RIGHTSRELAY_VOICE_CONFIG_PATH="$PWD\.models\en_US-libritts_r-medium.onnx.json"
.venv\Scripts\python.exe -m uvicorn rightsrelay.app:app --app-dir src --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>.

## Backblaze B2 mode

Create a **private** bucket with a bucket-scoped application key and set the
variables from `.env.example`. Never use a master key. Secrets stay server-side
and are excluded from responses and logs. Raw source scripts and canonical
Genblaze manifests remain private; the public `/proofs/{campaign_id}` endpoint
returns hashes and lineage fields without the prompt or filesystem paths.

```text
B2_KEY_ID=...
B2_APP_KEY=...
B2_BUCKET=rightsrelay-demo
B2_REGION=us-west-004
B2_PUBLIC_URL_BASE=
```

The app deliberately disables automatic bucket lifecycle changes. Audio is
read from private B2 by the service and returned through the same-origin media
route; no signed credential-bearing URL is persisted or exposed to the browser.

The private B2 bucket also stores a stable SQLite reverse-index snapshot. A
free Render instance restores it after an ephemeral-filesystem restart. If the
bucket is empty, `RIGHTSRELAY_SEED_DEMO` creates an idempotent before/after
example: Atlas revision one followed by a Nova replacement revision. Scripts,
audio, full manifests, and the index survive process restarts, while
content-addressed assets are deduplicated.

Anonymous mutations are serialized, capped at 24 campaigns, and rate-limited
per client in the public demo. A production deployment should add real user
authentication and tenant isolation.

## Tests

```powershell
$env:RIGHTSRELAY_TEST_MODEL_DIR="$PWD\.models"
pytest
```

Tests exercise real offline neural synthesis, canonical manifest verification,
audio and provenance tamper detection, redacted public proofs, reverse lookup,
idempotent demo seeding, and
revocation-triggered regeneration. No B2 credentials or network calls are
required by the default suite.

## Disclosure and licenses

- Application code: Apache-2.0.
- Genblaze: MIT.
- Piper TTS package: see the upstream package license.
- `en_US-libritts_r-medium` dataset/model attribution: CC BY 4.0, model card linked
  above.
- AI coding assistance was used during implementation. All generated changes
  were locally tested and are disclosed rather than presented as unaided work.
