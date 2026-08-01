# Security notes

RightsRelay is a public hackathon prototype, not a multi-tenant production
service. The deployed demo is designed around a private, dedicated Backblaze B2
bucket and a bucket-scoped application key. Never use a B2 master key.

## Public/private boundary

- Source scripts, canonical Genblaze manifests, and the SQLite reverse-index
  snapshot remain in private B2 storage.
- Public API responses exclude scripts, local paths, and storage URLs.
- `/proofs/{campaign_id}` exposes only hashes and selected lineage fields.
- `/media/{campaign_id}` returns generated audio through the same-origin
  service; it does not expose a signed or credential-bearing storage URL.
- Anonymous mutations are serialized, rate-limited, and capped for the demo.
  Real deployments must add authentication, tenant isolation, authorization,
  and a durable job queue.

## Dependency override

Genblaze Core 0.3.8 declares `pillow>=10,<12`. RightsRelay uses Genblaze's audio
and provenance paths, not image decoding. Pillow 11.3.0 is affected by known
2026 advisories, so `uv.lock` deliberately overrides the conservative upper
bound with Pillow 12.3.0. The full real-synthesis and provenance test suite runs
against that locked environment. Remove the override after upstream widens its
declared compatibility range.

## Reporting

Do not open a public issue containing credentials, signed URLs, private scripts,
or account data. Revoke any exposed bucket key immediately and replace it with a
new bucket-scoped key.
