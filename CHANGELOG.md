# Changelog

All notable changes to this project will be documented in this file.

## [0.1.1] - 2026-06-30
### Added
- **Turn-Based Context Packer**: Replaced destructive single-message knapsack compression with Turn-Based chunking (`[User -> Assistant -> Tool]`). This completely eliminates HTTP 400 template errors and orphaned messages during heavy context pruning.
- **Agent-Driven State Protocol**: Injected a survival protocol into the absolute bottom of the prompt (`packed_messages[-1]`) to bypass local model Recency Bias. This successfully forces the LLM to autonomously maintain a `YUMANI_STATE.md` file in the project workspace, preventing long-term context amnesia without relying on massive archive dumps.

### Fixed
- Fixed an issue where small models ignore state-retention instructions due to the token distance between the system prompt and the active conversation (Recency Bias).

## [0.1.0] - 2026-06-29
- Initial extraction of the local LLM harness core from the q36 field prototype.
- Generic OpenAI-compatible proxy and SQLite state store.
- Interactive CUI setup wizard (`yumani setup`).
