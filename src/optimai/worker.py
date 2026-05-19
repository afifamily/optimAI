"""MLX inference client — OpenAI-style chat completions worker with KV-cache reuse.

Talks to a local `mlx_lm.server` (DEC-017) running Qwen2.5-Coder-32B-Instruct-4bit
(DEC-018) on 127.0.0.1:1337 (DEC-012). The OpenAI-compatible HTTP API is the
abstraction boundary — backend can be swapped without touching this client.

Implementation deferred to session CLI #3 (see ROADMAP Phase 1 step 5).
"""
