#!/usr/bin/env bash
# setup-claude.sh — Bootstrap Claude Code Kontext nach git clone auf neuem PC
# Usage: cd DetourAI && bash setup-claude.sh
set -euo pipefail

# ─── Detect project path & Claude project key ───────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Claude Code project key: absolute path with / replaced by -
PROJECT_KEY="-$(echo "$PROJECT_DIR" | sed 's|^/||; s|/|-|g')"
MEMORY_DIR="$HOME/.claude/projects/$PROJECT_KEY/memory"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  DetourAI — Claude Code Setup                               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Project:    $PROJECT_DIR"
echo "Claude Key: $PROJECT_KEY"
echo ""

# ─── 1. Create memory directory ─────────────────────────────────────────────
echo "▸ Erstelle Memory-Verzeichnis..."
mkdir -p "$MEMORY_DIR"

# ─── 2. Write MEMORY.md ─────────────────────────────────────────────────────
echo "▸ Schreibe MEMORY.md..."
cat > "$MEMORY_DIR/MEMORY.md" << MEMEOF
# DetourAI — Project Memory

## Status: All 6 phases COMPLETE (2026-03-02)

## Project
Full-stack AI road trip planner. See MASTER_PROMPT.md for complete spec.
CLAUDE.md has overview. Stack: FastAPI + Redis + Celery + Vanilla JS + Nginx + Docker.

## Key paths
- Backend: $PROJECT_DIR/backend/
- Frontend: $PROJECT_DIR/frontend/
- Infra: $PROJECT_DIR/infra/
- Outputs: $PROJECT_DIR/outputs/

## Critical conventions
- All user-facing text in German
- Prices always in CHF
- TEST_MODE=true → all agents use claude-haiku-4-5
- Job state in Redis (key: job:{id}, TTL 24h)
- Claude calls via call_with_retry() — retry_helper.py
- JSON parsed via parse_agent_json() — json_parser.py
- Every API call logged with debug_logger.log(LogLevel.API, ...)
- Frontend API = '/api' (Nginx proxy, not localhost:8000)
- Nominatim: sleep 350ms between geocode calls

## Dev commands
\`\`\`bash
cd backend && python3 -m uvicorn main:app --reload --port 8000
cd backend && python3 -m pytest tests/ -v
cd backend && celery -A tasks worker --loglevel=info
docker compose up --build
\`\`\`

## Phase completion
- Phase 1: Project scaffold + Docker ✓
- Phase 2: Pydantic models ✓ (49 tests verify models)
- Phase 3: Backend core (11 endpoints + Redis) ✓
- Phase 4: 6 agents + orchestrator ✓
- Phase 5: Frontend (7 JS modules + HTML/CSS) ✓
- Phase 6: Tests — 49/49 passing ✓

## Agent models
| Agent | Prod | Test |
|-------|------|------|
| RouteArchitect | claude-opus-4-5 | claude-haiku-4-5 |
| StopOptionsFinder | claude-sonnet-4-5 | claude-haiku-4-5 |
| RegionPlanner | claude-opus-4-5 | claude-haiku-4-5 |
| AccommodationResearcher | claude-sonnet-4-5 | claude-haiku-4-5 |
| ActivitiesAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| RestaurantsAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| DayPlanner | claude-opus-4-5 | claude-haiku-4-5 |
| TravelGuideAgent | claude-sonnet-4-5 | claude-haiku-4-5 |
| TripAnalysisAgent | claude-sonnet-4-5 | claude-haiku-4-5 |

## Known issues / notes
- TEST_MODE=true is the default in .env.example
- Redis required for full backend operation

## Git commit workflow (USER PREFERENCE)
See also: [feedback_git_commits.md](feedback_git_commits.md) — no Co-Authored-By in commits.


After EVERY change: commit immediately as a patch release and push.
- Version format: x.x.y (e.g. v3.1.1, v3.1.2, ...)
- Steps:
  1. git add <changed files>
  2. git commit -m "fix/feat/perf/...: <description>"
  3. git tag vX.X.Y
  4. git push && git push --tags
MEMEOF

# ─── 3. Write feedback_git_commits.md ───────────────────────────────────────
echo "▸ Schreibe feedback_git_commits.md..."
cat > "$MEMORY_DIR/feedback_git_commits.md" << 'FBEOF'
---
name: No Co-Authored-By in commits
description: Do not add Co-Authored-By trailer to git commit messages
type: feedback
---

Do not add `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` (or any Co-Authored-By line) to git commit messages.

**Why:** User explicitly asked to stop — they don't want this attribution in commits.

**How to apply:** Every time you create a git commit, omit the Co-Authored-By line entirely. Commit message body should only contain the description, nothing else.
FBEOF

# ─── 4. Write ~/.claude/settings.json ────────────────────────────────────────
echo "▸ Schreibe ~/.claude/settings.json..."
mkdir -p "$HOME/.claude"
cat > "$HOME/.claude/settings.json" << 'SETTEOF'
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node \"$HOME/.claude/hooks/gsd-check-update.js\""
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node \"$HOME/.claude/hooks/gsd-context-monitor.js\""
          }
        ]
      }
    ],
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "afplay /System/Library/Sounds/Ping.aiff & osascript -e 'display notification \"Claude needs your input\" with title \"Claude Code\" sound name \"Ping\"'"
          }
        ]
      }
    ]
  },
  "statusLine": {
    "type": "command",
    "command": "node \"$HOME/.claude/hooks/gsd-statusline.js\""
  },
  "enabledPlugins": {
    "superpowers@claude-plugins-official": true,
    "frontend-design@claude-plugins-official": true,
    "prompt-improver@severity1-marketplace": true,
    "claude-mem@thedotmack": true
  },
  "extraKnownMarketplaces": {
    "severity1-marketplace": {
      "source": {
        "source": "github",
        "repo": "severity1/severity1-marketplace"
      }
    },
    "thedotmack": {
      "source": {
        "source": "github",
        "repo": "thedotmack/claude-mem"
      }
    }
  },
  "alwaysThinkingEnabled": false
}
SETTEOF

# ─── 5. Write clean .claude/settings.local.json in project ──────────────────
echo "▸ Schreibe .claude/settings.local.json (bereinigt)..."
mkdir -p "$PROJECT_DIR/.claude"
cat > "$PROJECT_DIR/.claude/settings.local.json" << 'LOCALEOF'
{
  "permissions": {
    "allow": [
      "Bash(git:*)", "Bash(python3:*)", "Bash(pip3:*)",
      "Bash(docker compose:*)", "Bash(docker build:*)",
      "Bash(ls:*)", "Bash(chmod +x:*)",
      "Bash(node:*)", "Bash(npm:*)",
      "Bash(gh:*)", "Bash(which:*)",
      "Edit", "Write", "WebSearch", "WebFetch",
      "Bash(git tag:*)", "Bash(ssh:*)",
      "mcp__plugin_claude-mem_mcp-search__smart_outline",
      "mcp__plugin_claude-mem_mcp-search__smart_unfold",
      "mcp__github__get_file_contents",
      "mcp__github__create_repository"
    ],
    "deny": [
      "Read(.env*)", "Read(~/.ssh/*)",
      "Bash(rm -rf:*)", "Bash(sudo:*)"
    ]
  },
  "enableAllProjectMcpServers": true,
  "enabledMcpjsonServers": ["github"]
}
LOCALEOF

# ─── 6. Install plugins ─────────────────────────────────────────────────────
echo ""
echo "▸ Installiere Claude Code Plugins..."
if command -v claude &> /dev/null; then
  claude plugins add superpowers@claude-plugins-official 2>/dev/null || echo "  ⚠ superpowers bereits installiert oder Fehler"
  claude plugins add frontend-design@claude-plugins-official 2>/dev/null || echo "  ⚠ frontend-design bereits installiert oder Fehler"
  claude plugins add prompt-improver@severity1-marketplace 2>/dev/null || echo "  ⚠ prompt-improver bereits installiert oder Fehler"
  claude plugins add claude-mem@thedotmack 2>/dev/null || echo "  ⚠ claude-mem bereits installiert oder Fehler"
  echo "  ✓ Plugin-Installation abgeschlossen"
else
  echo "  ⚠ 'claude' CLI nicht gefunden — Plugins manuell installieren:"
  echo "    claude plugins add superpowers@claude-plugins-official"
  echo "    claude plugins add frontend-design@claude-plugins-official"
  echo "    claude plugins add prompt-improver@severity1-marketplace"
  echo "    claude plugins add claude-mem@thedotmack"
fi

# ─── 7. Create backend/.env from .env.example if missing ────────────────────
echo ""
if [ ! -f "$PROJECT_DIR/backend/.env" ]; then
  if [ -f "$PROJECT_DIR/backend/.env.example" ]; then
    cp "$PROJECT_DIR/backend/.env.example" "$PROJECT_DIR/backend/.env"
    echo "▸ backend/.env erstellt aus .env.example"
    echo "  ⚠ API-Keys eintragen:"
    echo "    $PROJECT_DIR/backend/.env"
    echo "    → ANTHROPIC_API_KEY=sk-ant-..."
    echo "    → GOOGLE_MAPS_API_KEY=..."
  else
    echo "▸ ⚠ backend/.env.example nicht gefunden — .env manuell erstellen"
  fi
else
  echo "▸ backend/.env existiert bereits"
fi

# ─── 8. Checklist ────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Setup abgeschlossen! Manuelle Schritte:"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "  1. API-Keys in backend/.env eintragen:"
echo "     ANTHROPIC_API_KEY, GOOGLE_MAPS_API_KEY"
echo ""
echo "  2. .mcp.json für GitHub MCP erstellen:"
echo "     Neuen GitHub PAT generieren → settings/tokens"
echo "     Datei: $PROJECT_DIR/.mcp.json"
echo '     {"mcpServers":{"github":{"command":"npx",'
echo '      "args":["-y","@modelcontextprotocol/server-github"],'
echo '      "env":{"GITHUB_PERSONAL_ACCESS_TOKEN":"ghp_..."}}}}'
echo ""
echo "  3. Docker starten: docker compose up --build"
echo ""
echo "  4. Claude Code starten: claude"
echo "     → CLAUDE.md wird automatisch geladen"
echo "     → Memory + Plugins sind konfiguriert"
echo ""
