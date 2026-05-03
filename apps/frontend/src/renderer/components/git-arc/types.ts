/**
 * Git Arc Diagram Types
 * Types for hierarchical git commit visualization
 */

/** File change within a commit */
export interface GitArcFileChange {
  path: string;
  status: 'added' | 'modified' | 'deleted' | 'renamed';
  module: string; // Top-level directory (extracted from path)
  additions?: number;
  deletions?: number;
}

/** Commit with file changes for arc visualization */
export interface GitArcCommit {
  hash: string;
  fullHash: string;
  subject: string;
  body?: string;
  author: string;
  authorEmail: string;
  date: string; // ISO format
  files: GitArcFileChange[];
  // Derived for coloring
  commitType: 'feature' | 'fix' | 'refactor' | 'docs' | 'chore' | 'other';
  ageCategory: 'recent' | 'week' | 'older';
}

/** Uncommitted change (staged, unstaged, untracked) */
export interface UncommittedChange {
  path: string;
  status: 'staged' | 'unstaged' | 'untracked';
  module: string;
  additions?: number;
  deletions?: number;
}

/** Module node for overview diagram */
export interface ModuleNode {
  id: string;
  name: string; // Display name (e.g., "components")
  path: string; // Full path (e.g., "src/renderer/components")
  commitCount: number;
  uncommittedCount: number;
  lastCommitDate?: string;
  // For arc connections
  commits: string[]; // Commit hashes that touched this module
}

/** Arc connection between modules */
export interface ModuleArc {
  id: string;
  sourceModule: string; // Module ID
  targetModule: string; // Module ID
  commitHash: string;
  color: string;
  weight: number; // Number of files changed
}

/** File node for detail view */
export interface FileNode {
  id: string;
  name: string; // File name
  path: string; // Full path
  commitCount: number;
  hasUncommitted: boolean;
  commits: string[]; // Commit hashes
}

/** File arc for detail view */
export interface FileArc {
  id: string;
  sourceFile: string;
  targetFile: string;
  commitHash: string;
  color: string;
}

/** Complete git arc data structure */
export interface GitArcData {
  commits: GitArcCommit[];
  uncommitted: UncommittedChange[];
  modules: ModuleNode[];
  moduleArcs: ModuleArc[];
  // Metadata
  totalCommits: number;
  totalUncommitted: number;
  currentBranch: string;
  lastUpdated: string;
}

/** Module detail data */
export interface ModuleDetailData {
  module: ModuleNode;
  files: FileNode[];
  fileArcs: FileArc[];
  commits: GitArcCommit[]; // Commits that touched this module
  uncommitted: UncommittedChange[]; // Uncommitted in this module
}

/** Color palette for commits */
export const COMMIT_COLORS = {
  uncommitted: '#f59e0b', // Amber/Orange
  feature: '#22c55e', // Green
  fix: '#ef4444', // Red
  refactor: '#a855f7', // Purple
  docs: '#3b82f6', // Blue
  chore: '#6b7280', // Gray
  other: '#64748b', // Slate
  recent: '#10b981', // Emerald
  week: '#6366f1', // Indigo
  older: '#9ca3af', // Gray
} as const;

/** Color palette array for cycling through commits */
export const COMMIT_COLOR_PALETTE = [
  '#22c55e', // Green
  '#3b82f6', // Blue
  '#a855f7', // Purple
  '#f59e0b', // Amber
  '#ef4444', // Red
  '#06b6d4', // Cyan
  '#ec4899', // Pink
  '#84cc16', // Lime
  '#f97316', // Orange
  '#8b5cf6', // Violet
];

/** View state for arc diagram */
export type ArcDiagramView = 'overview' | 'detail';

/** Props for ArcDiagram component */
export interface ArcDiagramProps {
  data: GitArcData | null;
  selectedModule: string | null;
  onModuleClick: (moduleId: string) => void;
  isLoading: boolean;
  width?: number;
  height?: number;
}

/** Props for ModuleDetailView component */
export interface ModuleDetailViewProps {
  data: ModuleDetailData | null;
  onBack: () => void;
  isLoading: boolean;
  width?: number;
  height?: number;
}

/** Git arc panel state */
export interface GitArcPanelState {
  isCollapsed: boolean;
  view: ArcDiagramView;
  selectedModuleId: string | null;
  isLoading: boolean;
  error: string | null;
  data: GitArcData | null;
  moduleDetail: ModuleDetailData | null;
}
