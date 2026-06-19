# History settings

Control how long send history is kept and whether response bodies are stored on disk.

## Steps

1. Open **File → Settings…** → **History**.

## Retention

| Control | Purpose |
|---------|---------|
| **Keep history for (days)** | Delete entries older than this window |
| **Unlimited entries per day** | Disable the daily cap when checked |
| **Max entries per day** | Cap sends recorded per calendar day |

## Response bodies

| Control | Purpose |
|---------|---------|
| **Save response bodies** | Store response payload files for replay and inspection |
| **Max response size (MiB)** | Skip storing bodies larger than this limit |

The page shows where files are stored under your Postmark user data directory. Request metadata also lives in the project database.

## Privacy note

Stored snapshots can include auth headers and bodies as plaintext on disk. Tune retention and body saving for your security requirements.

## Related

- [Send history](../history/send-history.md)
- [Settings hub](README.md)
