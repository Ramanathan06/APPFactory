/**
 * Module Detail View Component
 * Shows detailed arc diagram for files within a module
 */

import { useEffect, useRef, useMemo } from 'react';
import * as d3 from 'd3';
import { ArrowLeft, FileCode, GitCommit, Clock } from 'lucide-react';
import { Button } from '../ui/button';
import type { ModuleDetailData } from './types';

interface ModuleDetailViewProps {
  data: ModuleDetailData | null;
  onBack: () => void;
  isLoading: boolean;
  width?: number;
  height?: number;
}

const COLORS = {
  uncommitted: '#f59e0b',
  node: '#374151',
  nodeHover: '#4b5563',
  nodeBorder: '#6b7280',
  text: '#e5e7eb',
  textMuted: '#9ca3af',
  hasUncommitted: '#fbbf24',
  arc: '#6366f1'
};

const COLOR_PALETTE = [
  '#22c55e', '#3b82f6', '#a855f7', '#f59e0b', '#ef4444',
  '#06b6d4', '#ec4899', '#84cc16', '#f97316', '#8b5cf6'
];

export function ModuleDetailView({
  data,
  onBack,
  isLoading,
  width = 240,
  height = 180
}: ModuleDetailViewProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  // Get top files by commit count
  const displayFiles = useMemo(() => {
    if (!data?.files) return [];
    return data.files.slice(0, 5);
  }, [data?.files]);

  useEffect(() => {
    if (!svgRef.current || !displayFiles.length) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const margin = { top: 10, right: 10, bottom: 20, left: 10 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Node dimensions
    const nodeWidth = Math.min(50, (innerWidth - 20) / displayFiles.length);
    const nodeHeight = 24;
    const nodeY = innerHeight - nodeHeight;

    // Scale for positioning
    const xScale = d3.scaleBand()
      .domain(displayFiles.map(f => f.id))
      .range([0, innerWidth])
      .padding(0.15);

    // Draw arcs between files
    if (data?.fileArcs) {
      const arcGroup = g.append('g').attr('class', 'arcs');
      const fileIds = new Set(displayFiles.map(f => f.id));

      // Group arcs
      const arcPairs = new Map<string, { count: number; color: string }>();
      data.fileArcs
        .filter(arc => fileIds.has(arc.sourceFile) && fileIds.has(arc.targetFile))
        .forEach((arc, i) => {
          const key = [arc.sourceFile, arc.targetFile].sort().join('|');
          if (!arcPairs.has(key)) {
            arcPairs.set(key, { count: 0, color: arc.color || COLOR_PALETTE[i % COLOR_PALETTE.length] });
          }
          arcPairs.get(key)!.count++;
        });

      arcPairs.forEach((info, key) => {
        const [source, target] = key.split('|');
        const sourceX = (xScale(source) || 0) + nodeWidth / 2;
        const targetX = (xScale(target) || 0) + nodeWidth / 2;

        if (sourceX === targetX) return;

        const midX = (sourceX + targetX) / 2;
        const arcHeight = Math.min(Math.abs(targetX - sourceX) * 0.5, innerHeight * 0.7);

        const path = d3.path();
        path.moveTo(sourceX, nodeY);
        path.quadraticCurveTo(midX, nodeY - arcHeight, targetX, nodeY);

        arcGroup
          .append('path')
          .attr('d', path.toString())
          .attr('fill', 'none')
          .attr('stroke', info.color)
          .attr('stroke-width', Math.min(1.5 + info.count * 0.5, 3))
          .attr('stroke-opacity', 0.7)
          .attr('stroke-linecap', 'round');
      });
    }

    // Draw file nodes
    const nodeGroup = g.append('g').attr('class', 'nodes');

    const nodes = nodeGroup
      .selectAll('g.node')
      .data(displayFiles)
      .enter()
      .append('g')
      .attr('class', 'node')
      .attr('transform', d => `translate(${xScale(d.id)},${nodeY})`);

    // Node rectangles
    nodes
      .append('rect')
      .attr('width', nodeWidth)
      .attr('height', nodeHeight)
      .attr('rx', 3)
      .attr('fill', COLORS.node)
      .attr('stroke', d => d.hasUncommitted ? COLORS.uncommitted : COLORS.nodeBorder)
      .attr('stroke-width', d => d.hasUncommitted ? 1.5 : 1);

    // File name labels
    nodes
      .append('text')
      .attr('x', nodeWidth / 2)
      .attr('y', nodeHeight / 2)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('fill', COLORS.text)
      .attr('font-size', '8px')
      .text(d => {
        const name = d.name.replace(/\.[^.]+$/, ''); // Remove extension
        return name.length > 6 ? name.slice(0, 5) + '..' : name;
      });

    // Commit count indicators
    nodes
      .filter(d => d.commitCount > 0)
      .append('circle')
      .attr('cx', nodeWidth - 3)
      .attr('cy', 3)
      .attr('r', 6)
      .attr('fill', COLORS.arc);

    nodes
      .filter(d => d.commitCount > 0)
      .append('text')
      .attr('x', nodeWidth - 3)
      .attr('y', 3)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('fill', 'white')
      .attr('font-size', '7px')
      .attr('font-weight', 'bold')
      .text(d => d.commitCount);

  }, [displayFiles, data?.fileArcs, width, height]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2">
        <span className="text-xs text-muted-foreground">No data available</span>
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="w-3 h-3 mr-1" />
          Back
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-2 py-1 border-b border-border">
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-1"
          onClick={onBack}
        >
          <ArrowLeft className="w-3 h-3" />
        </Button>
        <span className="text-xs font-medium truncate flex-1">
          {data.module.name}
        </span>
      </div>

      {/* Arc Diagram */}
      <div className="flex-1 min-h-0">
        <svg
          ref={svgRef}
          width={width}
          height={height}
          className="overflow-visible"
        />
      </div>

      {/* Stats */}
      <div className="flex items-center justify-between px-2 py-1 text-[10px] text-muted-foreground border-t border-border">
        <div className="flex items-center gap-1">
          <GitCommit className="w-3 h-3" />
          <span>{data.commits.length} commits</span>
        </div>
        <div className="flex items-center gap-1">
          <FileCode className="w-3 h-3" />
          <span>{data.files.length} files</span>
        </div>
        {data.uncommitted.length > 0 && (
          <div className="flex items-center gap-1 text-amber-500">
            <Clock className="w-3 h-3" />
            <span>{data.uncommitted.length} uncommitted</span>
          </div>
        )}
      </div>
    </div>
  );
}
