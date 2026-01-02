# Alphhaspace - Knowledge Transfer Document

## Executive Summary

Alphhaspace is a multi-agent autonomous coding framework that builds software through coordinated AI agent sessions. It combines an Electron desktop application (frontend) with a Python backend that orchestrates AI agents using the Claude Agent SDK.

---

## Table of Contents

1. [Technology Stack](#technology-stack)
2. [Project Structure](#project-structure)
3. [Architecture Overview](#architecture-overview)
4. [Frontend Architecture](#frontend-architecture)
5. [Backend Architecture](#backend-architecture)
6. [Core Workflows](#core-workflows)
7. [Agent System](#agent-system)
8. [Memory System](#memory-system)
9. [Security Model](#security-model)
10. [Configuration](#configuration)
11. [Development Commands](#development-commands)
12. [CI/CD Pipeline](#cicd-pipeline)
13. [Key Components Reference](#key-components-reference)
14. [Troubleshooting](#troubleshooting)

---

## Technology Stack

### Frontend
| Technology | Purpose |
|------------|---------|
| Electron | Desktop application framework |
| React 18 | UI library |
| TypeScript | Type-safe JavaScript |
| Vite | Build tool and dev server |
| Zustand | State management |
| TailwindCSS | Utility-first CSS |
| Radix UI | Accessible component primitives |
| react-i18next | Internationalization (EN/FR) |
| electron-builder | Cross-platform packaging |

### Backend
| Technology | Purpose |
|------------|---------|
| Python 3.12+ | Backend runtime |
| Claude Agent SDK | AI agent orchestration (NOT raw Anthropic API) |
| LadybugDB/Graphiti | Embedded graph database for memory |
| uv | Fast Python package manager |
| Git Worktrees | Isolated workspace management |

### Infrastructure
| Technology | Purpose |
|------------|---------|
| GitHub Actions | CI/CD automation |
| electron-vite | Electron + Vite integration |
| Dependabot | Automated dependency updates |

---

## Project Structure

```
alphhaspace/
├── apps/
│   ├── backend/                 # Python backend - ALL agent logic
│   │   ├── core/                # Client, auth, security
│   │   │   ├── client.py        # Claude SDK client factory
│   │   │   ├── security.py      # Command allowlisting
│   │   │   └── auth.py          # OAuth token management
│   │   ├── agents/              # Agent implementations
│   │   │   ├── planner.py       # Creates implementation plans
│   │   │   ├── coder.py         # Implements subtasks
│   │   │   ├── qa_reviewer.py   # Validates acceptance criteria
│   │   │   ├── qa_fixer.py      # Fixes QA issues
│   │   │   └── memory_manager.py # Session memory orchestration
│   │   ├── spec_agents/         # Spec creation agents
│   │   │   ├── gatherer.py      # Collects requirements
│   │   │   ├── researcher.py    # Validates integrations
│   │   │   ├── writer.py        # Creates spec.md
│   │   │   └── critic.py        # Self-critique
│   │   ├── integrations/        # External service integrations
│   │   │   ├── graphiti/        # Memory system
│   │   │   ├── github/          # GitHub automation
│   │   │   └── linear/          # Linear integration
│   │   ├── prompts/             # Agent system prompts (.md files)
│   │   ├── cli/                 # CLI utilities
│   │   │   └── worktree.py      # Git worktree isolation
│   │   ├── context/             # Project analysis
│   │   │   └── project_analyzer.py
│   │   ├── run.py               # Main execution entry point
│   │   ├── spec_runner.py       # Spec creation entry point
│   │   └── requirements.txt     # Python dependencies
│   │
│   └── frontend/                # Electron desktop UI
│       ├── src/
│       │   ├── main/            # Electron main process
│       │   │   ├── index.ts     # Main entry point
│       │   │   ├── ipc-handlers/ # IPC communication handlers
│       │   │   ├── agent/       # Agent queue management
│       │   │   └── project-store.ts
│       │   ├── preload/         # Electron preload scripts
│       │   ├── renderer/        # React application
│       │   │   ├── App.tsx      # Root component
│       │   │   ├── components/  # UI components
│       │   │   │   ├── AlphhaBoard.tsx    # Task board
│       │   │   │   ├── Sidebar.tsx        # Navigation
│       │   │   │   ├── roadmap/           # Roadmap views
│       │   │   │   ├── task-detail/       # Task details
│       │   │   │   └── ui/                # Base UI components
│       │   │   ├── stores/      # Zustand stores
│       │   │   └── hooks/       # Custom React hooks
│       │   └── shared/          # Shared utilities
│       │       ├── types/       # TypeScript types
│       │       ├── i18n/        # Internationalization
│       │       │   └── locales/
│       │       │       ├── en/  # English translations
│       │       │       └── fr/  # French translations
│       │       └── utils/       # Utility functions
│       ├── package.json
│       └── electron-builder.yml # Build configuration
│
├── guides/                      # Documentation
├── tests/                       # Test suite
├── scripts/                     # Build utilities
│   └── bump-version.js          # Version management
├── .github/
│   ├── workflows/
│   │   ├── ci.yml               # Continuous integration
│   │   ├── prepare-release.yml  # Auto-tag on version bump
│   │   └── release.yml          # Multi-platform builds
│   └── dependabot.yml           # Dependency updates
├── package.json                 # Root package.json
├── CLAUDE.md                    # AI assistant instructions
└── KNOWLEDGE_TRANSFER.md        # This file
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Electron Desktop App                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   Main Process  │  │  Preload Script │  │ Renderer (React)│  │
│  │   (Node.js)     │◄─┤     (Bridge)    ├─►│    (Browser)    │  │
│  └────────┬────────┘  └─────────────────┘  └─────────────────┘  │
│           │                                                      │
│           │ IPC Handlers                                         │
└───────────┼─────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Python Backend                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  Claude Agent   │  │     Agents      │  │    Graphiti     │  │
│  │      SDK        │  │ Planner/Coder/QA│  │  Memory System  │  │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  │
│           │                    │                    │            │
│           └────────────────────┼────────────────────┘            │
│                                │                                 │
│  ┌─────────────────────────────┼─────────────────────────────┐  │
│  │              Git Worktrees (Isolated Workspaces)          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External Services                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  Claude  │  │  GitHub  │  │  Linear  │  │  GitLab  │        │
│  │   API    │  │   API    │  │   API    │  │   API    │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Frontend Architecture

### Main Process (`apps/frontend/src/main/`)

The Electron main process handles:
- Window management
- IPC (Inter-Process Communication) handlers
- Python backend communication
- File system operations
- Native OS integrations

**Key Files:**
- `index.ts` - Application entry point, window creation
- `project-store.ts` - Project data persistence
- `ipc-handlers/` - All IPC handler modules
  - `claude-code.ts` - Claude CLI integration
  - `github/` - GitHub integration handlers
  - `gitlab/` - GitLab integration handlers
  - `ideation/` - AI ideation features

### Renderer Process (`apps/frontend/src/renderer/`)

React-based UI with the following structure:

**State Management (Zustand):**
```typescript
// stores/project-store.ts
interface ProjectStore {
  projects: Project[];
  activeProject: Project | null;
  setActiveProject: (project: Project) => void;
  // ...
}
```

**Key Components:**
- `AlphhaBoard.tsx` - Main task/spec board (renamed from KanbanBoard)
- `Sidebar.tsx` - Navigation sidebar
- `TaskDetailModal.tsx` - Task details view
- `roadmap/` - Roadmap visualization components

**Internationalization:**
```typescript
import { useTranslation } from 'react-i18next';

const { t } = useTranslation(['navigation', 'common']);
// Usage: t('navigation:items.kanban') → "Alphha Board"
```

**Translation Files:**
- `src/shared/i18n/locales/en/` - English
- `src/shared/i18n/locales/fr/` - French

---

## Backend Architecture

### Core Components

**Client Factory (`core/client.py`):**
```python
from core.client import create_client

client = create_client(
    project_dir=project_dir,
    spec_dir=spec_dir,
    model="claude-sonnet-4-5-20250929",
    agent_type="coder",  # planner, coder, qa_reviewer, qa_fixer
    max_thinking_tokens=None
)
```

**Security (`core/security.py`):**
- Dynamic command allowlisting based on project stack
- Bash command isolation
- Filesystem permission controls

**Authentication (`core/auth.py`):**
- OAuth token management for Claude SDK

### Agent System

**Spec Creation Pipeline (`spec_runner.py`):**

| Complexity | Phases |
|------------|--------|
| SIMPLE | Discovery → Quick Spec → Validate (3 phases) |
| STANDARD | Discovery → Requirements → Context → Spec → Plan → Validate (6 phases) |
| COMPLEX | Full pipeline with Research and Self-Critique (8 phases) |

**Implementation Pipeline (`run.py`):**

1. **Planner Agent** - Creates subtask-based implementation plan
2. **Coder Agent** - Implements subtasks (can spawn subagents)
3. **QA Reviewer** - Validates acceptance criteria
4. **QA Fixer** - Resolves issues in a loop

---

## Core Workflows

### Creating and Running Specs

```bash
cd apps/backend

# Interactive spec creation
python spec_runner.py --interactive

# Create from task description
python spec_runner.py --task "Add user authentication"

# Force complexity level
python spec_runner.py --task "Fix button" --complexity simple

# Run autonomous build
python run.py --spec 001

# List all specs
python run.py --list
```

### Workspace Management

```bash
# Review changes in isolated worktree
python run.py --spec 001 --review

# Merge completed build into project
python run.py --spec 001 --merge

# Discard build
python run.py --spec 001 --discard
```

### QA Validation

```bash
# Run QA manually
python run.py --spec 001 --qa

# Check QA status
python run.py --spec 001 --qa-status
```

### Spec Directory Structure

Each spec in `.alphhaspace/specs/XXX-name/` contains:
```
XXX-feature-name/
├── spec.md                    # Feature specification
├── requirements.json          # Structured user requirements
├── context.json               # Discovered codebase context
├── implementation_plan.json   # Subtask-based plan
├── qa_report.md               # QA validation results
├── QA_FIX_REQUEST.md          # Issues to fix (when rejected)
└── graphiti/                  # Memory data
```

---

## Agent System

### Agent Types

| Agent | Prompt File | Purpose |
|-------|-------------|---------|
| Planner | `prompts/planner.md` | Creates implementation plan with subtasks |
| Coder | `prompts/coder.md` | Implements individual subtasks |
| Coder Recovery | `prompts/coder_recovery.md` | Recovers from stuck/failed subtasks |
| QA Reviewer | `prompts/qa_reviewer.md` | Validates acceptance criteria |
| QA Fixer | `prompts/qa_fixer.md` | Fixes QA-reported issues |

### Spec Agents

| Agent | Prompt File | Purpose |
|-------|-------------|---------|
| Gatherer | `prompts/spec_gatherer.md` | Collects user requirements |
| Researcher | `prompts/spec_researcher.md` | Validates external integrations |
| Writer | `prompts/spec_writer.md` | Creates spec.md document |
| Critic | `prompts/spec_critic.md` | Self-critique using ultrathink |

### Branching Strategy

```
main (user's branch)
└── alphhaspace/{spec-name}  ← spec branch (isolated worktree)
```

**Key Principles:**
- ONE branch per spec
- NO automatic pushes to GitHub
- User reviews in `.worktrees/{spec-name}/`
- User controls merge and push

---

## Memory System

### Graphiti Memory

Located in `apps/backend/integrations/graphiti/`:

```
graphiti/
├── queries_pkg/
│   ├── graphiti.py    # Main GraphitiMemory class
│   ├── client.py      # LadybugDB client wrapper
│   ├── queries.py     # Graph query operations
│   ├── search.py      # Semantic search logic
│   └── schema.py      # Graph schema definitions
```

**Features:**
- Graph database with semantic search
- Session insights extraction
- Cross-session context sharing

**Multi-Provider Support:**
- LLM: OpenAI, Anthropic, Azure, Ollama, Google AI
- Embedders: OpenAI, Voyage AI, Azure, Ollama, Google AI

**Usage:**
```python
from integrations.graphiti.memory import get_graphiti_memory

memory = get_graphiti_memory(spec_dir, project_dir)
context = memory.get_context_for_session("Implementing feature X")
memory.add_session_insight("Pattern: use React hooks for state")
```

---

## Security Model

### Three-Layer Defense

1. **OS Sandbox** - Bash command isolation
2. **Filesystem Permissions** - Operations restricted to project directory
3. **Command Allowlist** - Dynamic allowlist from project analysis

Security profile cached in `.alphhaspace-security.json`

---

## Configuration

### Environment Variables (`apps/backend/.env`)

```bash
# Claude Authentication
CLAUDE_CODE_OAUTH_TOKEN=your-token

# Graphiti Memory
GRAPHITI_ENABLED=true
ANTHROPIC_API_KEY=your-key

# Optional: Electron E2E Testing
ELECTRON_MCP_ENABLED=true
ELECTRON_DEBUG_PORT=9222

# Optional: Linear Integration
LINEAR_API_KEY=your-key
```

### Frontend Configuration

- `electron-builder.yml` - Build configuration
- `electron.vite.config.ts` - Vite + Electron configuration
- `tailwind.config.js` - TailwindCSS theme

---

## Development Commands

### Setup

```bash
# Install all dependencies from root
npm run install:all

# Or install separately:
cd apps/backend && uv venv && uv pip install -r requirements.txt
cd apps/frontend && npm install

# Set up OAuth token
claude setup-token
```

### Development

```bash
# Start development server (with E2E testing support)
npm run dev

# Build production
npm run build

# Run Electron app
npm start
```

### Testing

```bash
# Backend tests
apps/backend/.venv/bin/pytest tests/ -v

# Run specific test
apps/backend/.venv/bin/pytest tests/test_security.py::test_bash_command_validation -v

# Skip slow tests
apps/backend/.venv/bin/pytest tests/ -m "not slow"

# From root
npm run test:backend
```

### Version Management

```bash
# Bump version (creates commit, no tag)
node scripts/bump-version.js patch   # 2.8.0 → 2.8.1
node scripts/bump-version.js minor   # 2.8.0 → 2.9.0
node scripts/bump-version.js major   # 2.8.0 → 3.0.0
```

---

## CI/CD Pipeline

### Workflows

**1. CI (`ci.yml`)** - Runs on every push/PR
- Linting and type checking
- Frontend tests
- Backend tests
- E2E tests

**2. Prepare Release (`prepare-release.yml`)** - Runs on main push
- Detects version changes
- Creates git tag automatically

**3. Release (`release.yml`)** - Runs on tag creation
- Builds for all platforms:
  - macOS (x64, arm64) - `.dmg`, `.zip`
  - Windows - `.exe`
  - Linux - `.AppImage`, `.deb`, `.rpm`
- Creates GitHub release with binaries

**4. Dependabot (`dependabot.yml`)**
- Weekly npm dependency updates
- Weekly pip dependency updates

### Release Process

```bash
# 1. Create feature branch
git checkout -b feature/my-feature

# 2. Make changes and commit
git add . && git commit -m "feat: add feature"

# 3. Bump version
node scripts/bump-version.js patch

# 4. Push and create PR
git push origin feature/my-feature
gh pr create --base main

# 5. Merge PR → GitHub Actions automatically:
#    - Creates tag
#    - Builds all platforms
#    - Creates release
```

---

## Key Components Reference

### Frontend Components

| Component | Path | Purpose |
|-----------|------|---------|
| AlphhaBoard | `components/AlphhaBoard.tsx` | Main task board |
| Sidebar | `components/Sidebar.tsx` | Navigation |
| TaskDetailModal | `components/task-detail/TaskDetailModal.tsx` | Task details |
| RoadmapTabs | `components/roadmap/RoadmapTabs.tsx` | Roadmap views |
| RoadmapAlphhaView | `components/RoadmapAlphhaView.tsx` | Roadmap board view |

### Backend Modules

| Module | Path | Purpose |
|--------|------|---------|
| create_client | `core/client.py` | Claude SDK client factory |
| security | `core/security.py` | Command allowlisting |
| planner | `agents/planner.py` | Planning agent |
| coder | `agents/coder.py` | Implementation agent |
| worktree | `cli/worktree.py` | Git worktree management |
| graphiti | `integrations/graphiti/` | Memory system |

### IPC Handlers

| Handler | Path | Purpose |
|---------|------|---------|
| claude-code | `ipc-handlers/claude-code.ts` | Claude CLI integration |
| github | `ipc-handlers/github/` | GitHub features |
| gitlab | `ipc-handlers/gitlab/` | GitLab features |
| ideation | `ipc-handlers/ideation/` | AI ideation |

---

## Troubleshooting

### Common Issues

**1. Import Resolution Errors**
```
Failed to resolve import "./components/AlphhaBoard"
```
**Solution:** Ensure file names match import paths. After renaming, restart dev server.

**2. Version Bump Fails on Beta**
```
❌ Error: Invalid version format: 2.7.2-beta.10
```
**Solution:** Manually edit version in:
- `apps/frontend/package.json`
- `package.json`
- `apps/backend/__init__.py`

**3. Python Environment Issues**
```bash
# Recreate virtual environment
cd apps/backend
rm -rf .venv
uv venv && uv pip install -r requirements.txt
```

**4. Electron DevTools Errors**
```
Request Autofill.enable failed
```
**Note:** These are cosmetic Chrome DevTools Protocol errors and can be ignored.

**5. Git Push Rejected**
```bash
# Force push after history rewrite
git push --force origin main
```

---

## Contact & Resources

- **Repository:** https://github.com/shibinsp/APPFactory
- **Documentation:** See `guides/` directory
- **AI Instructions:** See `CLAUDE.md`

---

*Last Updated: January 2026*
*Version: 2.7.3*
