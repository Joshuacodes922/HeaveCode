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

## How it works

- A session's messages are stored in PostgreSQL and reloaded when its session ID is reused.
- Current tools: `list_files`, `read_file`, and `write_file`.
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

- Supports simulataneous tool calls. Current tool calls avaliable are list_files, read_files, write_files.

- Does not support Ollama's tool calls. 

- The model sends a response containing a tool call, such as read_file. It is then the developer's responsibility to execute that tool and make another model call, adding the model's previous response and the tool's result to the existing conversation context.

   The model receives this updated conversation and can see that read_file was executed and what it returned. Based on that new information and the original task, it can decide what to do next—for example, sending another tool call for write_file.

   The developer executes write_file, adds the model's tool call and the tool result to the conversation, and calls the model again.

   This loop continues until the model returns a response with no tool calls, at which point the agent treats that response as the final answer and stops.
