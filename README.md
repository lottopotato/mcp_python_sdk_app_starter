# Python MCP Server Starters

Two starters for MCP servers built on the Python MCP SDK. Both share the same server core
(`StreamableServer`: Streamable HTTP, uvicorn, middleware) and differ in **who calls the server**.

| | [`app_server/`](app_server) | [`tool_server/`](tool_server) |
|---|---|---|
| Called by | Your own programs (web client, internal services) | LLM agents (Claude Desktop / Code, your agent host) |
| Responses | JSON your program parses (`status`, `code`, ...) | Markdown for the model + `structuredContent` for programs |
| Tool / argument descriptions | Short | Written as the model's manual (limits in the schema) |
| Errors | Error fields inside a normal response | MCP tool errors (`isError: true`) the model can act on |
| Auth | Your choice (e.g. token as a tool argument) | `Authorization: Bearer` header, one middleware |
| Assembly | Module-level `SERVER` (import builds it) | `create_tool_server()` factory, parts injected (testable) |
| Extras | REST twins of the tools, CORS, Gunicorn runner, resources | Stateless by default, startup/shutdown hooks, `/health`, tests |

Pick one folder and use it as the root of your new project; each has its own `pyproject.toml`, `uv.lock`,
`.env_example` and README.

```text
app_server/    # starter for an app-facing MCP API server
tool_server/   # starter for an agent-facing MCP tool server
```

## Note: Cloning Without Git History

By default, `git clone` downloads the repository history and creates a `.git` folder. If you want to start a new project with the starter pack's files but without its Git history, use one of the methods below.

### 1. Use `git clone --depth 1` (recommended)

This fetches only the latest commit and its required Git data, rather than the full history. It still creates a `.git` folder, so **delete the `.git` folder after cloning** to keep only the files.

```bash
# 1. Clone only the latest commit
git clone --depth 1 <repository URL>

# 2. Move into the folder
cd <folder-name>

# 3. Remove the git folder (Linux/macOS)
rm -rf .git

# Remove the git folder (Windows PowerShell)
rm -Recurse -Force .git
```

### 2. Use `npx degit` (cleanest method)

If you have Node.js installed, using the `degit` tool is the most convenient option. It copies only the code and never creates a `.git` folder at all.

```bash
npx degit <username>/<repository-name>/tool_server <new-folder-name>   # or .../app_server
```

### 3. Use `git archive` (requires server support)

This requires support from the remote server and downloads the code as an archive without `.git`. (Note that some services, such as GitHub, restrict remote `git archive` for security reasons.)

```bash
git archive --remote=<repository URL> HEAD -o latest.zip
```

### 4. Download a ZIP with curl or wget

Instead of a Git command, this uses the ZIP download link provided by the web service. (GitHub example below.)

```bash
curl -L https://github.com/<user>/<repo>/archive/refs/heads/main.zip -o code.zip
unzip code.zip
```

### Summary

- **Fastest Git command:** run `git clone --depth 1`, then delete the `.git` folder
- **Cleanest tool:** use `npx degit`
- **GUI users:** click **[Code] -> [Download ZIP]** on the GitHub page
