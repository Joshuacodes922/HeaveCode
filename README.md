# Mini Coding Agent

A small terminal coding agent using an Ollama model, safe workspace tools, and PostgreSQL-backed chat sessions.

## Setup

1. Install Python 3.11+, [Docker](https://docs.docker.com/get-docker/), and [Ollama](https://ollama.com/).
2. Create and activate a virtual environment, then install dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Review `.env` and choose a real local database password. Start PostgreSQL:

   ```powershell
   docker compose up -d
   ```

4. Download the configured model, then start the agent:

   ```powershell
   ollama pull qwen2.5-coder:7b
   python main.py
   ```

Press Enter at the session prompt to create a new session, or enter a prior ID to continue it. The agent can list, read, and write files within `WORKSPACE_DIR`.

Set `VERBOSE_TOOLS=true` in `.env` to print tool calls and their results as the agent works.

## Reliability and safety

- `write_file` displays a unified diff and requires terminal approval by default. Set `REQUIRE_WRITE_APPROVAL=false` only for trusted, non-interactive runs.
- Tool arguments are validated. Reads and writes stay inside `WORKSPACE_DIR`, cannot access `.env`, `.git`, or `.venv`, and are limited to 100 KB of UTF-8 text.
- Agent work is bounded by `MAX_TOOL_ROUNDS`; session history is bounded by `MAX_HISTORY_MESSAGES`; one transient Ollama request is retried.
- Structured JSONL events are written to `AGENT_LOG_PATH` (default: `logs/agent.jsonl`). They record model latency, tool requests/results, and agent lifecycle events.

Run the automated checks with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The starter regression cases are in `evals/coding_tasks.jsonl`. Add real successful and failed tasks there whenever the prompts, model, or tools change.

## Vulkan RAG integration

The agent uses the copied `vk-rag` FastAPI service as a retrieval tool; it does not call the service's answer-generation endpoint. This lets the coding agent decide when it needs Vulkan evidence, then use the returned sections while it inspects and edits code.

Start the RAG service in a separate terminal after its PostgreSQL database has been started and its documentation has been ingested:

```powershell
cd vk-rag
docker compose up -d postgres
# Create/configure vk-rag\.env and install vk-rag\requirements.txt once.
uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Set `VULKAN_RAG_URL=http://127.0.0.1:8000` in the coding-agent `.env` (already configured locally), then restart `python main.py`. For Vulkan validation messages, VUIDs, API rules, extensions, features, synchronization, and shader-interface questions, the agent can call `search_vulkan_docs` and cite results as `[document, section, pages]`.

Set `VULKAN_RAG_URL=` to disable retrieval and run the generic agent without the RAG tool.

## How it works

- A session's messages are stored in PostgreSQL and reloaded when its session ID is reused.
- Current tools: `list_files`, `read_file`, `write_file`, `delete_file`, and—when `VULKAN_RAG_URL` is configured—`search_vulkan_docs`.
- Add future tools in `tools.py`, then register their schemas and functions in `TOOL_SCHEMAS` and `TOOL_FUNCTIONS`.

### Data flow

```text
USER
  |
  | "update test.py with binary search code"
  |
  v
+-----------------------------+
| MODEL CALL #1               |
|                             |
| "I need to read test.py"    |
|                             |
| -> read_file                |
+-------------+---------------+
              |
              v
        PYTHON TOOL
              |
              v
          read_file()
              |
              v
        FILE CONTENTS
              |
              v
+-----------------------------+
| MODEL CALL #2               |
|                             |
| "Now I'll update the file" |
|                             |
| -> write_file               |
+-------------+---------------+
              |
              v
        PYTHON TOOL
              |
              v
         write_file()
              |
              v
       "Wrote test.py"
              |
              v
+-----------------------------+
| MODEL CALL #3               |
|                             |
| "The task is complete."     |
|                             |
| NO TOOL CALL                |
+-------------+---------------+
              |
              v
            RETURN
```

The agent adds each model response and tool result to the conversation, then calls the model again. The loop ends when the model returns a response with no tool calls.


DOCUMENTING MY CODING AGENT V1:

- Supports sessions which contain all the messages which are stored in databases which are loaded everytime the session is loaded

- Supports multiple tool calls. Current tools are `list_files`, `read_file`, `write_file`, and approval-gated `delete_file`.

- Does not support Ollama's tool calls. 

- The model sends a response containing a tool call, such as read_file. It is then the developer's responsibility to execute that tool and make another model call, adding the model's previous response and the tool's result to the existing conversation context.

   The model receives this updated conversation and can see that read_file was executed and what it returned. Based on that new information and the original task, it can decide what to do next—for example, sending another tool call for write_file.

   The developer executes write_file, adds the model's tool call and the tool result to the conversation, and calls the model again.

   This loop continues until the model returns a response with no tool calls, at which point the agent treats that response as the final answer and stops.

- So basically the code spits out a json if there are calls, which then gets called in code. If calls is None, then the text message is send back ending the agent loop. 

- So the flow is:
   - Message history in that conversation is fetched and the user prompt is added to that
   - A conversation variable is set containing system prompt + messages[-max convo length]
   - The agent loop runs 10 times which is the default max_tool_count. 
      - It creates an assistant message which either spits out a json with the tools it needs or a finishing message
      - We keep running the loop until we getting that finished message
      - Tools are then called and executed and added to the conversation variable we created which will be passed into the next tool call. 

- The assistant message is created after sending a prompt containing system prompt + convo history. Now the json for calls is supposed to come under the response.tool_calls section but for now it comes inside content which i then get through a helper function.  

- To add a tool, you write the function inside ToolExecutor class and then add the info to tool schema and execute function. 