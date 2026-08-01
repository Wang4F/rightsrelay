# RightsRelay three-minute demo

Do not record credentials, signed URLs, email addresses, account information,
or the browser password manager. Record only after the app badge says
`Backblaze B2 connected` and the real private-B2 smoke test has passed.

## 0:00–0:18 — The problem

Show the RightsRelay hero.

> Generative-media teams can create hundreds of voice derivatives. But when one
> synthetic voice profile should no longer be used, finding every affected
> file, replacing it, and proving what changed is still largely manual.
> RightsRelay turns that decision into a traceable workflow.

## 0:18–0:38 — Architecture and scope

Show the pipeline and `Backblaze B2 connected` badge.

> RightsRelay combines local neural voice generation, Genblaze provenance, a
> reverse lineage index, and private Backblaze B2 storage. It records an
> operational profile decision; it does not claim to determine legal consent or
> license validity.

## 0:38–1:10 — Generate

Restore Atlas if needed. Create a campaign with Atlas and play its audio.

> Piper runs locally through a custom Genblaze provider, so the campaign text is
> not sent to a hosted model API. Genblaze connects the source asset, model,
> profile, parameters, and generated WAV in one run. This is a real 22.05
> kilohertz WAV, not a mocked placeholder.

## 1:10–1:35 — Verify without leaking the prompt

Click `Proof`, then `Verify`.

> The public proof exposes the run ID, provider, model, hashes, and replacement
> fields, but withholds the prompt and internal paths. Verify parses the private
> canonical manifest, verifies its hash against the index, and recomputes the
> WAV SHA-256.

## 1:35–2:05 — Revoke and relay

Create a second Atlas campaign, then click `Revoke & relay`.

> Now the operator revokes Atlas and selects Nova. RightsRelay generates every
> replacement first, verifies it, then commits the voice decision and all
> revisions atomically. Both current derivatives advance to Nova while Atlas is
> visibly revoked.

## 2:05–2:30 — Follow the chain

Open a regenerated proof and the history endpoint.

> The replacement is not an overwrite. It records the trigger, previous run ID,
> and previous manifest hash. Revision history keeps both generations, so a
> reviewer can follow the exact before-and-after chain.

## 2:30–2:48 — Show real B2 evidence

Open the B2 object browser with account details cropped. Show the
`rightsrelay/assets`, `rightsrelay/manifests`, and `rightsrelay/state` prefixes.

> Genblaze stores scripts, audio, and full manifests in private B2. The state
> snapshot restores the reverse index after an ephemeral restart, and
> content-addressable keys avoid duplicating identical assets.

## 2:48–3:00 — Close

Return to the dashboard and briefly show `9 passed` plus the clean audit.

> RightsRelay demonstrates a practical path from profile revocation to
> regenerated, durable, and mechanically verifiable synthetic media. Revoke
> once, regenerate every affected derivative.
