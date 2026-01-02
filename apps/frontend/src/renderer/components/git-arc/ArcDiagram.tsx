/**
 * Arc Diagram Component
 * D3-based visualization showing modules as nodes with arc connections
 */

import { useEffect, useRef, useMemo } from 'react';
import * as d3 from 'd3';
import type { GitArcData, ModuleNode, ModuleArc, COMMIT_COLORS } from './types';

interface ArcDiagramProps {
  data: GitArcData | null;
  onModuleClick: (moduleId: string) => void;
  isLoading: boolean;
  width?: number;
  height?: number;
}

// Color constants
const COLORS = {
  uncommitted: '#f59e0b',
  node: '#374151',
  nodeHover: '#4b5563',
  nodeBorder: '#6b7280',
  text: '#e5e7eb',
  textMuted: '#9ca3af',
  background: '#1f2937',
  arc: '#6366f1'
};

const COLOR_PALETTE = [
  '#22c55e', '#3b82f6', '#a855f7', '#f59e0b', '#ef4444',
  '#06b6d4', '#ec4899', '#84cc16', '#f97316', '#8b5cf6'
];

export function ArcDiagram({
  data,
  onModuleClick,
  isLoading,
  width = 240,
  height = 200
}: ArcDiagramProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  // Process modules for display (top 6 by commit count)
  const displayModules = useMemo(() => {
    if (!data?.modules) return [];
    return data.modules.slice(0, 6);
  }, [data?.modules]);

  // Create arcs between modules
  const arcs = useMemo(() => {
    if (!data?.moduleArcs || displayModules.length < 2) return [];

    const moduleIds = new Set(displayModules.map(m => m.id));
    return data.moduleArcs.filter(
      arc => moduleIds.has(arc.sourceModule) && moduleIds.has(arc.targetModule)
    ).slice(0, 10); // Limit arcs for performance
  }, [data?.moduleArcs, displayModules]);

  useEffect(() => {
    if (!svgRef.current || !displayModules.length) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const margin = { top: 20, right: 10, bottom: 30, left: 10 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    // Create main group
    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Node dimensions
    const nodeWidth = Math.min(60, (innerWidth - 20) / displayModules.length);
    const nodeHeight = 30;
    const nodeY = innerHeight - nodeHeight - 10;

    // Scale for positioning nodes
    const xScale = d3.scaleBand()
      .domain(displayModules.map(m => m.id))
      .range([0, innerWidth])
      .padding(0.2);

    // Draw arcs first (behind nodes)
    const arcGroup = g.append('g').attr('class', 'arcs');

    // Group arcs by source-target pair
    const arcPairs = new Map<string, { count: number; color: string }>();
    arcs.forEach((arc, i) => {
      const key = [arc.sourceModule, arc.targetModule].sort().join('|');
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
      const arcHeight = Math.min(Math.abs(targetX - sourceX) * 0.4, innerHeight * 0.6);

      const path = d3.path();
      path.moveTo(sourceX, nodeY);
      path.quadraticCurveTo(midX, nodeY - arcHeight, targetX, nodeY);

      arcGroup
        .append('path')
        .attr('d', path.toString())
        .attr('fill', 'none')
        .attr('stroke', info.color)
        .attr('stroke-width', Math.min(2 + info.count * 0.5, 4))
        .attr('stroke-opacity', 0.6)
        .attr('stroke-linecap', 'round');
    });

    // Draw nodes
    const nodeGroup = g.append('g').attr('class', 'nodes');

    const nodes = nodeGroup
      .selectAll('g.node')
      .data(displayModules)
      .enter()
      .append('g')
      .attr('class', 'node')
      .attr('transform', d => `translate(${xScale(d.id)},${nodeY})`)
      .style('cursor', 'pointer')
      .on('click', (_, d) => onModuleClick(d.id))
      .on('mouseenter', function() {
        d3.select(this).select('rect').attr('fill', COLORS.nodeHover);
      })
      .on('mouseleave', function() {
        d3.select(this).select('rect').attr('fill', COLORS.node);
      });

    // Node rectangles
    nodes
      .append('rect')
      .attr('width', nodeWidth)
      .attr('height', nodeHeight)
      .attr('rx', 4)
      .attr('fill', COLORS.node)
      .attr('stroke', d => d.uncommittedCount > 0 ? COLORS.uncommitted : COLORS.nodeBorder)
      .attr('stroke-width', d => d.uncommittedCount > 0 ? 2 : 1);

    // Node labels
    nodes
      .append('text')
      .attr('x', nodeWidth / 2)
      .attr('y', nodeHeight / 2)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('fill', COLORS.text)
      .attr('font-size', '9px')
      .attr('font-weight', '500')
      .text(d => {
        const name = d.name.length > 8 ? d.name.slice(0, 7) + '..' : d.name;
        return name;
      });

    // Commit count badges
    nodes
      .filter(d => d.commitCount > 0)
      .append('circle')
      .attr('cx', nodeWidth - 4)
      .attr('cy', 4)
      .attr('r', 8)
      .attr('fill', COLORS.arc);

    nodes
      .filter(d => d.commitCount > 0)
      .append('text')
      .attr('x', nodeWidth - 4)
      .attr('y', 4)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('fill', 'white')
      .attr('font-size', '8px')
      .attr('font-weight', 'bold')
      .text(d => d.commitCount > 99 ? '99+' : d.commitCount);

    // Uncommitted indicator
    nodes
      .filter(d => d.uncommittedCount > 0)
      .append('circle')
      .attr('cx', 4)
      .attr('cy', 4)
      .attr('r', 4)
      .attr('fill', COLORS.uncommitted);

  }, [displayModules, arcs, width, height, onModuleClick]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500" />
      </div>
    );
  }

  if (!data || displayModules.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
        No git data available
      </div>
    );
  }

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        width={width}
        height={height}
        className="overflow-visible"
      />

      {/* Legend */}
      <div className="flex flex-wrap gap-2 px-2 mt-1 text-[10px]">
        <div className="flex items-center gap-1">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: COLORS.uncommitted }}
          />
          <span className="text-muted-foreground">Uncommitted</span>
        </div>
        <div className="flex items-center gap-1">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: COLORS.arc }}
          />
          <span className="text-muted-foreground">{data.totalCommits} commits</span>
        </div>
      </div>
    </div>
  );
}
