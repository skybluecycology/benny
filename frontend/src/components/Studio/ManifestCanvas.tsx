import React, { useMemo } from 'react';
import { ReactFlow, Background, Controls, MiniMap } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { RunRecord, SwarmManifest, TaskStatus } from '../../types/manifest';
import { manifestToCanvas } from '../../types/manifest';

interface Props {
  manifest: SwarmManifest;
  run?: RunRecord | null;
}

const STATUS_COLOR: Record<TaskStatus, string> = {
  pending: '#64748b',
  running: '#3b82f6',
  completed: '#10b981',
  failed: '#ef4444',
  skipped: '#6b7280',
};

/**
 * ManifestCanvas — renders a SwarmManifest's plan as an xyflow graph.
 *
 * If a run is provided, each node is colored by its status in that run
 * (overlaying live execution state on top of the declarative plan).
 */
export default function ManifestCanvas({ manifest, run }: Props) {
  const { nodes, edges } = useMemo(() => {
    const projected = manifestToCanvas(manifest, run ?? null);

    // xyflow expects { data, position } — our helper already returns that.
    // We wrap each node with a tiny custom node label to avoid pulling the
    // full studio node palette. Keep styling inline so the component is
    // self-contained.
    const styledNodes = projected.nodes.map((n) => {
      const status = (n.data.status as TaskStatus) ?? 'pending';
      const color = STATUS_COLOR[status] ?? '#64748b';
      const isPillar = Boolean(n.data.is_pillar);
      return {
        ...n,
        type: 'default',
        style: {
          background: '#0b0e13',
          color: 'white',
          border: `1.5px solid ${color}`,
          borderRadius: 8,
          padding: '6px 10px',
          fontSize: 11,
          boxShadow: isPillar ? `0 0 0 2px ${color}40` : undefined,
          minWidth: 180,
        },
        data: {
          label: (
            <div className="text-left">
              <div className="text-[10px] uppercase opacity-60">
                wave {String(n.data.wave ?? 0)} · {String(n.data.complexity ?? 'medium')}
                {isPillar ? ' · pillar' : ''}
              </div>
              <div className="truncate font-medium">{String(n.data.label ?? n.id)}</div>
              {n.data.skill_hint ? (
                <div className="mt-0.5 text-[10px] text-emerald-400">
                  {String(n.data.skill_hint)}
                </div>
              ) : null}
              <div className="mt-0.5 text-[10px]" style={{ color }}>
                {status}
              </div>
            </div>
          ),
        },
      };
    });

    const styledEdges = projected.edges.map((e) => ({
      ...e,
      style: { stroke: 'rgba(255,255,255,0.25)', strokeWidth: 1.3 },
    }));

    return { nodes: styledNodes, edges: styledEdges };
  }, [manifest, run]);

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes as any}
        edges={edges as any}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1f2937" gap={24} />
        <MiniMap pannable zoomable maskColor="rgba(0,0,0,0.6)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
