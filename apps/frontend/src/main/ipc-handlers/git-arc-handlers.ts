/**
 * Git Arc Diagram IPC Handlers
 * Fetches git commit data with file changes for arc visualization
 */

import { ipcMain } from 'electron';
import { execFileSync } from 'child_process';
import { existsSync } from 'fs';
import { IPC_CHANNELS } from '../../shared/constants';
import type { IPCResult } from '../../shared/types';
import { projectStore } from '../project-store';
import { getToolPath } from '../cli-tool-manager';

// Types for git arc data
interface GitArcFileChange {
  path: string;
  status: 'added' | 'modified' | 'deleted' | 'renamed';
  module: string;
}

interface GitArcCommit {
  hash: string;
  fullHash: string;
  subject: string;
  author: string;
  authorEmail: string;
  date: string;
  files: GitArcFileChange[];
  commitType: 'feature' | 'fix' | 'refactor' | 'docs' | 'chore' | 'other';
  ageCategory: 'recent' | 'week' | 'older';
}

interface UncommittedChange {
  path: string;
  status: 'staged' | 'unstaged' | 'untracked';
  module: string;
}

interface ModuleNode {
  id: string;
  name: string;
  path: string;
  commitCount: number;
  uncommittedCount: number;
  lastCommitDate?: string;
  commits: string[];
}

interface ModuleArc {
  id: string;
  sourceModule: string;
  targetModule: string;
  commitHash: string;
  color: string;
  weight: number;
}

interface GitArcData {
  commits: GitArcCommit[];
  uncommitted: UncommittedChange[];
  modules: ModuleNode[];
  moduleArcs: ModuleArc[];
  totalCommits: number;
  totalUncommitted: number;
  currentBranch: string;
  lastUpdated: string;
}

interface ModuleDetailData {
  module: ModuleNode;
  files: Array<{
    id: string;
    name: string;
    path: string;
    commitCount: number;
    hasUncommitted: boolean;
    commits: string[];
  }>;
  fileArcs: Array<{
    id: string;
    sourceFile: string;
    targetFile: string;
    commitHash: string;
    color: string;
  }>;
  commits: GitArcCommit[];
  uncommitted: UncommittedChange[];
}

// Color palette for commits
const COMMIT_COLORS = [
  '#22c55e', '#3b82f6', '#a855f7', '#f59e0b', '#ef4444',
  '#06b6d4', '#ec4899', '#84cc16', '#f97316', '#8b5cf6'
];

/**
 * Extract module (top-level directory) from file path
 */
function extractModule(filePath: string): string {
  const parts = filePath.split('/');
  // For paths like src/components/Button.tsx, return "src/components"
  // For paths like package.json, return "root"
  if (parts.length === 1) return 'root';
  if (parts.length === 2) return parts[0];
  return `${parts[0]}/${parts[1]}`;
}

/**
 * Determine commit type from subject
 */
function getCommitType(subject: string): GitArcCommit['commitType'] {
  const lower = subject.toLowerCase();
  if (lower.startsWith('feat') || lower.includes('add') || lower.includes('new')) return 'feature';
  if (lower.startsWith('fix') || lower.includes('bug')) return 'fix';
  if (lower.startsWith('refactor') || lower.includes('refactor')) return 'refactor';
  if (lower.startsWith('docs') || lower.includes('documentation')) return 'docs';
  if (lower.startsWith('chore') || lower.includes('chore')) return 'chore';
  return 'other';
}

/**
 * Determine age category of commit
 */
function getAgeCategory(dateStr: string): GitArcCommit['ageCategory'] {
  const commitDate = new Date(dateStr);
  const now = new Date();
  const daysDiff = (now.getTime() - commitDate.getTime()) / (1000 * 60 * 60 * 24);

  if (daysDiff < 1) return 'recent';
  if (daysDiff < 7) return 'week';
  return 'older';
}

/**
 * Parse file status character to type
 */
function parseFileStatus(statusChar: string): GitArcFileChange['status'] {
  switch (statusChar) {
    case 'A': return 'added';
    case 'M': return 'modified';
    case 'D': return 'deleted';
    case 'R': return 'renamed';
    default: return 'modified';
  }
}

/**
 * Get git commits with file changes
 */
function getCommitsWithFiles(projectPath: string, limit: number = 50): GitArcCommit[] {
  try {
    // Get commits with file changes using --name-status
    const output = execFileSync(
      getToolPath('git'),
      ['log', `--pretty=format:%h|%H|%s|%an|%ae|%aI`, '--name-status', `-${limit}`],
      {
        cwd: projectPath,
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
        maxBuffer: 10 * 1024 * 1024 // 10MB buffer
      }
    );

    const commits: GitArcCommit[] = [];
    let currentCommit: GitArcCommit | null = null;

    const lines = output.split('\n');
    for (const line of lines) {
      if (!line.trim()) {
        if (currentCommit) {
          commits.push(currentCommit);
          currentCommit = null;
        }
        continue;
      }

      // Check if this is a commit line (contains |)
      if (line.includes('|') && line.split('|').length >= 6) {
        if (currentCommit) {
          commits.push(currentCommit);
        }

        const [hash, fullHash, subject, author, authorEmail, date] = line.split('|');
        currentCommit = {
          hash,
          fullHash,
          subject,
          author,
          authorEmail,
          date,
          files: [],
          commitType: getCommitType(subject),
          ageCategory: getAgeCategory(date)
        };
      } else if (currentCommit) {
        // This is a file status line (e.g., "M\tsrc/file.ts")
        const match = line.match(/^([AMDRT])\t(.+)$/);
        if (match) {
          const [, statusChar, filePath] = match;
          currentCommit.files.push({
            path: filePath,
            status: parseFileStatus(statusChar),
            module: extractModule(filePath)
          });
        }
      }
    }

    // Don't forget the last commit
    if (currentCommit) {
      commits.push(currentCommit);
    }

    return commits;
  } catch (error) {
    console.error('[GitArc] Error getting commits:', error);
    return [];
  }
}

/**
 * Get uncommitted changes
 */
function getUncommittedChanges(projectPath: string): UncommittedChange[] {
  try {
    const output = execFileSync(
      getToolPath('git'),
      ['status', '--porcelain'],
      {
        cwd: projectPath,
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe']
      }
    );

    const changes: UncommittedChange[] = [];
    const lines = output.split('\n').filter(l => l.trim());

    for (const line of lines) {
      const staged = line[0];
      const unstaged = line[1];
      const filePath = line.slice(3).trim();

      let status: UncommittedChange['status'];
      if (staged === '?' && unstaged === '?') {
        status = 'untracked';
      } else if (staged !== ' ' && staged !== '?') {
        status = 'staged';
      } else {
        status = 'unstaged';
      }

      changes.push({
        path: filePath,
        status,
        module: extractModule(filePath)
      });
    }

    return changes;
  } catch (error) {
    console.error('[GitArc] Error getting uncommitted changes:', error);
    return [];
  }
}

/**
 * Get current branch name
 */
function getCurrentBranch(projectPath: string): string {
  try {
    const output = execFileSync(
      getToolPath('git'),
      ['rev-parse', '--abbrev-ref', 'HEAD'],
      {
        cwd: projectPath,
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe']
      }
    );
    return output.trim();
  } catch {
    return 'unknown';
  }
}

/**
 * Build module nodes and arcs from commits
 */
function buildModuleGraph(
  commits: GitArcCommit[],
  uncommitted: UncommittedChange[]
): { modules: ModuleNode[], arcs: ModuleArc[] } {
  const moduleMap = new Map<string, ModuleNode>();
  const arcs: ModuleArc[] = [];
  let colorIndex = 0;

  // Build modules from commits
  for (const commit of commits) {
    const modulesInCommit = new Set<string>();

    for (const file of commit.files) {
      modulesInCommit.add(file.module);

      if (!moduleMap.has(file.module)) {
        moduleMap.set(file.module, {
          id: file.module,
          name: file.module.split('/').pop() || file.module,
          path: file.module,
          commitCount: 0,
          uncommittedCount: 0,
          commits: []
        });
      }

      const module = moduleMap.get(file.module)!;
      if (!module.commits.includes(commit.hash)) {
        module.commits.push(commit.hash);
        module.commitCount++;
        if (!module.lastCommitDate || commit.date > module.lastCommitDate) {
          module.lastCommitDate = commit.date;
        }
      }
    }

    // Create arcs between modules touched by same commit
    const moduleList = Array.from(modulesInCommit);
    const color = COMMIT_COLORS[colorIndex % COMMIT_COLORS.length];

    for (let i = 0; i < moduleList.length - 1; i++) {
      arcs.push({
        id: `${commit.hash}-${moduleList[i]}-${moduleList[i + 1]}`,
        sourceModule: moduleList[i],
        targetModule: moduleList[i + 1],
        commitHash: commit.hash,
        color,
        weight: 1
      });
    }

    colorIndex++;
  }

  // Add uncommitted changes to modules
  for (const change of uncommitted) {
    if (!moduleMap.has(change.module)) {
      moduleMap.set(change.module, {
        id: change.module,
        name: change.module.split('/').pop() || change.module,
        path: change.module,
        commitCount: 0,
        uncommittedCount: 0,
        commits: []
      });
    }
    moduleMap.get(change.module)!.uncommittedCount++;
  }

  return {
    modules: Array.from(moduleMap.values()).sort((a, b) => b.commitCount - a.commitCount),
    arcs
  };
}

/**
 * Register git arc IPC handlers
 */
export function registerGitArcHandlers(): void {
  console.log('[GitArc] Registering Git Arc handlers');

  // Get complete git arc data for a project
  ipcMain.handle(
    IPC_CHANNELS.GIT_ARC_GET_DATA,
    async (_, projectId: string): Promise<IPCResult<GitArcData>> => {
      try {
        const project = projectStore.getProject(projectId);
        if (!project) {
          return { success: false, error: 'Project not found' };
        }

        if (!existsSync(project.path)) {
          return { success: false, error: 'Project directory does not exist' };
        }

        const commits = getCommitsWithFiles(project.path, 50);
        const uncommitted = getUncommittedChanges(project.path);
        const currentBranch = getCurrentBranch(project.path);
        const { modules, arcs } = buildModuleGraph(commits, uncommitted);

        const data: GitArcData = {
          commits,
          uncommitted,
          modules,
          moduleArcs: arcs,
          totalCommits: commits.length,
          totalUncommitted: uncommitted.length,
          currentBranch,
          lastUpdated: new Date().toISOString()
        };

        return { success: true, data };
      } catch (error) {
        console.error('[GitArc] Error getting arc data:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : 'Failed to get git arc data'
        };
      }
    }
  );

  // Get detail data for a specific module
  ipcMain.handle(
    IPC_CHANNELS.GIT_ARC_GET_MODULE_DETAIL,
    async (_, projectId: string, modulePath: string): Promise<IPCResult<ModuleDetailData>> => {
      try {
        const project = projectStore.getProject(projectId);
        if (!project) {
          return { success: false, error: 'Project not found' };
        }

        const commits = getCommitsWithFiles(project.path, 50);
        const uncommitted = getUncommittedChanges(project.path);

        // Filter commits that touch this module
        const moduleCommits = commits.filter(c =>
          c.files.some(f => f.module === modulePath)
        );

        // Build file nodes from commits
        const fileMap = new Map<string, {
          id: string;
          name: string;
          path: string;
          commitCount: number;
          hasUncommitted: boolean;
          commits: string[];
        }>();

        const fileArcs: ModuleDetailData['fileArcs'] = [];
        let colorIndex = 0;

        for (const commit of moduleCommits) {
          const filesInCommit = commit.files
            .filter(f => f.module === modulePath)
            .map(f => f.path);

          for (const filePath of filesInCommit) {
            if (!fileMap.has(filePath)) {
              fileMap.set(filePath, {
                id: filePath,
                name: filePath.split('/').pop() || filePath,
                path: filePath,
                commitCount: 0,
                hasUncommitted: false,
                commits: []
              });
            }

            const file = fileMap.get(filePath)!;
            if (!file.commits.includes(commit.hash)) {
              file.commits.push(commit.hash);
              file.commitCount++;
            }
          }

          // Create arcs between files in same commit
          const color = COMMIT_COLORS[colorIndex % COMMIT_COLORS.length];
          for (let i = 0; i < filesInCommit.length - 1; i++) {
            fileArcs.push({
              id: `${commit.hash}-${filesInCommit[i]}-${filesInCommit[i + 1]}`,
              sourceFile: filesInCommit[i],
              targetFile: filesInCommit[i + 1],
              commitHash: commit.hash,
              color
            });
          }
          colorIndex++;
        }

        // Mark files with uncommitted changes
        const moduleUncommitted = uncommitted.filter(u => u.module === modulePath);
        for (const change of moduleUncommitted) {
          if (fileMap.has(change.path)) {
            fileMap.get(change.path)!.hasUncommitted = true;
          } else {
            fileMap.set(change.path, {
              id: change.path,
              name: change.path.split('/').pop() || change.path,
              path: change.path,
              commitCount: 0,
              hasUncommitted: true,
              commits: []
            });
          }
        }

        const { modules } = buildModuleGraph(commits, uncommitted);
        const moduleNode = modules.find(m => m.path === modulePath) || {
          id: modulePath,
          name: modulePath.split('/').pop() || modulePath,
          path: modulePath,
          commitCount: moduleCommits.length,
          uncommittedCount: moduleUncommitted.length,
          commits: moduleCommits.map(c => c.hash)
        };

        const data: ModuleDetailData = {
          module: moduleNode,
          files: Array.from(fileMap.values()).sort((a, b) => b.commitCount - a.commitCount),
          fileArcs,
          commits: moduleCommits,
          uncommitted: moduleUncommitted
        };

        return { success: true, data };
      } catch (error) {
        console.error('[GitArc] Error getting module detail:', error);
        return {
          success: false,
          error: error instanceof Error ? error.message : 'Failed to get module detail'
        };
      }
    }
  );

  console.log('[GitArc] Git Arc handlers registered');
}
