# RightsRelay — Devpost submission draft

> Replace `[LIVE_APP_URL]`, `[GITHUB_REPO_URL]`, and `[DEMO_VIDEO_URL]` only
> after each destination has been opened and verified. Do not remove this note
> until the private-B2 smoke test passes.

## Tagline

Revoke once. Regenerate every affected synthetic-voice derivative.

## Inspiration

Generative-audio workflows often end with disconnected WAV files. When a media
team decides that a synthetic voice profile should no longer be used, operators
may have no reliable way to identify every affected campaign, replace those
derivatives, and prove what changed. A storage URL alone cannot answer which
source script, model, voice profile, and prior asset produced the current file.

RightsRelay addresses that operational gap. It does not decide whether consent,
a license, or a contract is legally valid; it records and executes a team's
operational profile decisions.

## What it does

RightsRelay creates synthetic-voice campaign assets and maintains a reverse
lineage index. An operator submits a source script and selects an active voice
profile. A local neural TTS model generates a real WAV through Genblaze while
the app records the source hash, provider, model, voice profile, output hash,
run ID, and canonical manifest hash.

When a profile is revoked, RightsRelay finds every current campaign using it,
generates replacements with an approved profile, verifies every candidate, and
then commits the profile decision and all campaign revisions atomically. Each
new manifest records the run ID and manifest hash it replaced.

Reviewers can play the current audio, inspect a privacy-safe public proof, view
revision history, and recompute the current WAV hash. Full prompts, canonical
manifests, and the reverse-index snapshot remain in private Backblaze B2.

## How we built it

RightsRelay is a Python 3.11 and FastAPI application with a lightweight HTML,
CSS, and JavaScript interface. A custom `PiperTTSProvider` implements
Genblaze's `SyncProvider` contract and exposes Piper `en_US-libritts_r-medium`
as an audio provider.

The source script is registered with `Pipeline.ingest`. A second Genblaze
pipeline produces the audio with the source attached as an external input.
Run metadata records campaign ID, revision, voice profile, operational use
window, trigger, source-manifest hash, and—when applicable—the exact run and
manifest being replaced.

In B2 mode, `ObjectStorageSink` and `S3StorageBackend.for_backblaze` store
source assets, WAV files, and canonical manifests under a dedicated prefix.
Content-addressable keys deduplicate identical bytes. A private B2 state object
restores the SQLite reverse index after an ephemeral Render restart, and the
same-origin media route fetches private audio without exposing credentials or
signed URLs.

The public demo serializes generation, caps campaigns, and rate-limits anonymous
mutations. Production use would add authentication and tenant isolation.

## How RightsRelay uses Genblaze

- `Pipeline.ingest` registers and hashes source scripts.
- A custom Genblaze provider performs real local neural audio generation.
- External input assets connect each derivative to its source.
- Pipeline metadata records operational and replacement lineage.
- Canonical manifests and asset SHA-256 values provide mechanical verification.
- `ObjectStorageSink` persists assets and manifests to B2.

Genblaze is the orchestration and provenance layer, not a decorative wrapper.

## How RightsRelay uses Backblaze B2

Backblaze B2 is the private durable layer for source scripts, generated WAV
files, canonical Genblaze manifests, and the reverse-lineage index snapshot.
RightsRelay uses a bucket-scoped key and never persists presigned URLs. Media is
fetched by the server and returned through a same-origin endpoint. Every
regeneration creates a new run and manifest instead of overwriting prior
evidence.

## Challenges

1. Adapting offline Piper TTS to Genblaze while returning complete audio asset
   metadata: media type, duration, size, URL, and SHA-256.
2. Preserving replacement lineage without mutating history, and making the
   multi-campaign revocation commit atomic after generation succeeds.
3. Keeping canonical manifests verifiable while not exposing their full prompts
   through public API responses.
4. Making a free ephemeral deployment restore its index and private media from
   B2 rather than merely uploading objects once.
5. Keeping the product boundary honest: a workflow status is not proof of legal
   consent or licensing.

## Accomplishments

- Real 22.05 kHz local neural voice generation with no paid inference API.
- A custom Piper provider inside real Genblaze ingest and generation pipelines.
- One-action profile revocation and regeneration of affected current campaigns.
- Atomic campaign/history updates with exact before-and-after hash links.
- Private B2 media, manifests, and restart-safe index snapshots.
- Privacy-safe public proofs plus audio and canonical-manifest tamper detection.
- Nine automated tests, a clean Ruff check, a pinned model revision with SHA-256
  verification, and a dependency audit with no known vulnerabilities.

## What we learned

Durable storage and provenance solve different problems. B2 keeps bytes
available; Genblaze explains how those bytes were produced. Application-level
replacement links and a reverse index turn independent manifests into an
actionable operations workflow. We also learned that honest boundaries improve
the design: RightsRelay records observable facts and operator decisions instead
of pretending to infer legal truth.

## What's next

- Authenticated roles, tenant isolation, approval steps, and audit events.
- A transactional hosted database plus a background queue for large batches.
- External revocation events from licensing or consent-management systems.
- Reminders and workflow actions for recorded operational-use dates.
- Additional Genblaze-compatible voice providers and models.
- Retry controls, structured tracing, and partial-failure recovery.

## Providers and models

- Provider ID: `piper-local`, custom `PiperTTSProvider(SyncProvider)`.
- Engine: Piper TTS 1.6.0; local inference only.
- Model: `en_US-libritts_r-medium`, 904 speakers, 22,050 Hz.
- Training: fine-tuned from English lessac medium on LibriTTS-R
  `train-clean-360`; dataset license CC BY 4.0.
- Demo aliases: Atlas = speaker 0, Nova = speaker 1. They are synthetic labels,
  not claims about real people or cloned voices.
- Orchestration: Genblaze Core 0.3.8 and genblaze-s3 0.3.6.
- Storage: private Backblaze B2 with content-addressable assets.
- Hosted AI providers: none in the running application.

## AI assistance disclosure

OpenAI Codex was used as an AI coding assistant for implementation, debugging,
test creation, interface copy, and submission drafting. The application was
executed and mechanically tested; AI assistance is disclosed rather than
presented as unaided work. Codex is not a runtime media provider. The entrant
remains responsible for reviewing the repository, demo, claims, and submission.

## Links

- Working app: [LIVE_APP_URL]
- Source: [GITHUB_REPO_URL]
- Demo video: [DEMO_VIDEO_URL]
- Piper model card: https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/libritts_r/medium/MODEL_CARD

