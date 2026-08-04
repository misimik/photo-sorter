# Taste (Continuously Learned by [CommandCode][cmd])

[cmd]: https://commandcode.ai/

# Deployment
See [deployment/taste.md](deployment/taste.md)

# Workflow
- User prefers commands to run without per-command approval prompts (attempted `cmd --yolo` to enable auto-approval instead of approving each command individually). Confidence: 0.4

# Product / App Design
- For the photo-sorter, user explicitly wants per-folder actions — review, grouping, tournament, and export scoped to a single selected folder at a time, not whole-library operations. He wants to separate photos into small actionable chunks ("anything greater than one folder is too much"; "I am lazy"). Confidence: 0.9
- User wants fast, incremental testing loops: while testing is ongoing, avoid full-library scans (e.g., 15k photos) and support scanning/testing one small folder at a time so issues surface quickly without waiting for a huge scan. Confidence: 0.85
- When a previous project attempt already has a good/polished interface, user prefers the assistant to read and reuse that prior UI work rather than rebuild the interface from scratch — the prior attempt's problems were infrastructure/dockerization, not the UI. Confidence: 0.6
