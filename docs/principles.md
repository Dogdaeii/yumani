# Principles

Yumani is designed to solve the two most critical failure modes when running frontier coding agents (like Claude Code, Aider, or OpenHands) on local hardware: **Memory Exhaustion (OOM)** and **Cognitive Degradation (Amnesia & Recency Bias)**.

Below are the core architectural principles that allow Yumani to safely throttle unlimited agent context into limited local VRAM without breaking the LLM.

## The Core Problem

When an autonomous agent runs in a loop, its context window grows infinitely with file reads, terminal outputs, and past tool calls.
If you send a 100K token payload to a local model (e.g., 20B parameters) running on a machine with 24GB VRAM, the backend (e.g., vLLM, llama.cpp, MLX) will immediately crash with an Out-Of-Memory (OOM) error.

Naively truncating the oldest messages to avoid OOM creates two new fatal problems:
1. **Template Collapse (HTTP 400)**: Chat API specifications demand strict structural sequences (e.g., a `tool_call` from the assistant MUST be followed by a `tool_result` from the user). Slicing the message list arbitrarily often leaves orphaned tool calls, causing the upstream API to reject the request entirely.
2. **Amnesia**: If you drop the old messages, the agent instantly forgets what project it is working on, what files it edited, and what its overall plan was.

Yumani solves these with two architectural pillars.

---

## Principle 1: Turn-Based Context Packing (Yumani 4.0)

**Goal**: Prevent OOM while maintaining perfect API template integrity.

Instead of dropping individual messages (which breaks the strict `user -> assistant -> tool` sequence), Yumani's Context Packer groups messages into atomic **"Turns"**. 
A single turn encapsulates the full cycle of a thought process:
`[User Request] + [Assistant Tool Call] + [Tool Execution Result]`

When the total token count exceeds the `safe_input_tokens` threshold defined in your profile, Yumani drops the oldest *entire turns* block by block until the payload fits in VRAM. 

This guarantees that:
- The local endpoint will **never OOM**, no matter how long the agent runs.
- The local endpoint will **never throw HTTP 400 errors** because orphaned tool calls or malformed message sequences are mathematically impossible.

---

## Principle 2: Agent-Driven State Protocol (Yumani 5.0)

**Goal**: Prevent amnesia when old context is dropped, and defeat "Recency Bias" in smaller models.

Because Yumani aggressively drops old turns to save VRAM, the agent *will* eventually lose its long-term memory. 
To solve this, Yumani shifts the burden of long-term memory from the LLM's ephemeral context window directly to the filesystem.

When Yumani drops context, it triggers a **Survival Protocol**. The agent is explicitly commanded to maintain a `YUMANI_STATE.md` (or wiki) file in its working directory to write down its progress, architecture decisions, and current plan before the turn ends. If the agent loses context, it is instructed to simply read that file to recover its memory.

### Defeating Recency Bias
A major flaw in small/mid-sized models (under 30B parameters) is **Recency Bias**: if you put critical survival instructions in the `System Prompt` (at the very top of a 20K token context), the model will completely ignore them by the time it generates a response at the bottom.

Yumani elegantly bypasses this limitation. Instead of placing the Survival Protocol in the system prompt, Yumani **dynamically injects the instructions into the absolute bottom of the payload (`packed_messages[-1]`)** right before sending it to the model. 

Because the strict survival command is literally the *last thing* the model reads before generating tokens, even highly distractible small models will obediently pause to update their `YUMANI_STATE.md` file, perfectly preserving their long-term cognitive continuity across hundreds of turns.
