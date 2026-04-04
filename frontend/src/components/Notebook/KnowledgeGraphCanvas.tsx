import { useEffect, useRef, useState, useCallback } from 'react';
import ForceGraph3D from '3d-force-graph';
import { Share2, Zap, Clock, AlertTriangle, RefreshCw, Maximize2, Minimize2 } from 'lucide-react';

interface GraphNode {
  id: string;
  name: string;
  labels: string[];
  domain: string;
  created_at: string;
  // Force-graph internal
  x?: number;
  y?: number;
  z?: number;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
  predicate: string;
  description: string;
  pattern: string;
  source_doc: string;
  created_at: string;
  timestamp: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface KnowledgeGraphCanvasProps {
  onConceptClick?: (concept: string) => void;
  workspace?: string;
}

const EDGE_COLORS: Record<string, string> = {
  RELATES_TO: '#8b5cf6',
  SOURCED_FROM: '#6366f1',
  CONFLICTS_WITH: '#ef4444',
  ANALOGOUS_TO: '#f59e0b',
};

const NODE_COLORS: Record<string, string> = {
  Concept: '#8b5cf6',
  Source: '#06b6d4',
};

export default function KnowledgeGraphCanvas({ onConceptClick, workspace = 'default' }: KnowledgeGraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] });
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; node: GraphNode } | null>(null);

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    try {
      const timestamp = Date.now();
      const [graphRes, statsRes] = await Promise.all([
        fetch(`http://localhost:8005/api/graph/full?workspace=${workspace}&t=${timestamp}`),
        fetch(`http://localhost:8005/api/graph/stats?workspace=${workspace}&t=${timestamp}`)
      ]);

      if (graphRes.ok) {
        const data = await graphRes.json();
        setGraphData(data);
      }
      if (statsRes.ok) {
        const data = await statsRes.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to fetch graph:', err);
    } finally {
      setLoading(false);
    }
  }, [workspace]);

  // Initial load
  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  // Render 3D force graph
  useEffect(() => {
    if (!containerRef.current || graphData.nodes.length === 0) return;

    // Clean up any existing graph instance
    if (graphRef.current) {
      graphRef.current._destructor?.();
      containerRef.current.innerHTML = '';
    }

    const graph = ForceGraph3D()(containerRef.current)
      .backgroundColor('rgba(0,0,0,0)')
      .nodeLabel((node: any) => `<div style="background:rgba(15,15,30,0.9);padding:6px 10px;border-radius:6px;color:#e2e8f0;font-size:12px;border:1px solid rgba(139,92,246,0.3)"><strong>${node.name}</strong><br/><span style="opacity:0.7">${(node.labels || []).join(', ')}</span></div>`)
      .nodeColor((node: any) => {
        const label = (node.labels || [])[0] || 'Concept';
        return NODE_COLORS[label] || '#8b5cf6';
      })
      .nodeVal((node: any) => {
        const label = (node.labels || [])[0] || 'Concept';
        return label === 'Source' ? 3 : 6;
      })
      .nodeOpacity(0.92)
      .linkColor((link: any) => EDGE_COLORS[link.type] || '#4a5568')
      .linkWidth(1.5)
      .linkOpacity(0.6)
      .linkDirectionalArrowLength(4)
      .linkDirectionalArrowRelPos(1)
      .linkLabel((link: any) => `<div style="background:rgba(15,15,30,0.9);padding:4px 8px;border-radius:4px;color:#e2e8f0;font-size:11px;border:1px solid rgba(99,102,241,0.3)">${link.predicate || link.type}</div>`)
      .onNodeClick((node: any) => {
        setSelectedNode(node as GraphNode);
        if (onConceptClick) onConceptClick(node.name);
      })
      .onNodeRightClick((node: any, event: MouseEvent) => {
        event.preventDefault();
        setContextMenu({
          x: event.clientX,
          y: event.clientY,
          node: node as GraphNode
        });
      })
      .width(containerRef.current.clientWidth)
      .height(containerRef.current.clientHeight);

    // Convert edges to link format
    const links = graphData.edges.map(e => ({
      ...e,
      source: e.source,
      target: e.target,
    }));

    graph.graphData({
      nodes: graphData.nodes.map(n => ({ ...n })),
      links
    });

    graphRef.current = graph;

    // Resize observer
    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current) {
        graph.width(containerRef.current.clientWidth);
        graph.height(containerRef.current.clientHeight);
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
    };
  }, [graphData, onConceptClick]);

  const handleCrossDomain = async (concept: string, domain: string) => {
    setContextMenu(null);
    try {
      const res = await fetch('http://localhost:8005/api/graph/cross-domain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          concept,
          target_domain: domain,
          workspace
        })
      });
      if (res.ok) {
        const data = await res.json();
        alert(`Cross-Domain Result:\n\n${JSON.stringify(data.result, null, 2)}`);
      }
    } catch (err) {
      console.error('Cross-domain analogy failed:', err);
    }
  };

  return (
    <div className={`knowledge-graph-canvas ${isFullscreen ? 'fullscreen' : ''}`}>
      {/* Toolbar */}
      <div className="graph-toolbar">
        <div className="graph-toolbar-left">
          <Share2 size={14} style={{ color: 'var(--primary)' }} />
          <span className="graph-toolbar-title">Knowledge Graph</span>
          {stats && (
            <span className="graph-toolbar-stats">
              {stats.concepts} concepts · {stats.relationships} relations
              {stats.conflicts > 0 && <span className="conflict-badge"> · {stats.conflicts} ⚠️</span>}
              {stats.analogies > 0 && <span className="analogy-badge"> · {stats.analogies} 🔗</span>}
            </span>
          )}
        </div>
        <div className="graph-toolbar-right">
          <button className="btn-icon btn-ghost" onClick={fetchGraph} title="Refresh">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          <button className="btn-icon btn-ghost" onClick={() => setIsFullscreen(!isFullscreen)} title="Toggle Fullscreen">
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      {/* 3D Canvas */}
      <div 
        ref={containerRef} 
        className="graph-3d-container"
        onClick={() => setContextMenu(null)}
      />

      {/* Empty state */}
      {graphData.nodes.length === 0 && !loading && (
        <div className="graph-empty-state">
          <Share2 size={32} style={{ opacity: 0.4 }} />
          <p>No knowledge graph yet</p>
          <span>Ingest text to build the relational graph</span>
        </div>
      )}

      {/* Legend */}
      <div className="graph-legend">
        <div className="legend-item">
          <span className="legend-dot" style={{ background: NODE_COLORS.Concept }} />
          <span>Concept</span>
        </div>
        <div className="legend-item">
          <span className="legend-dot" style={{ background: NODE_COLORS.Source }} />
          <span>Source</span>
        </div>
        <div className="legend-item">
          <span className="legend-line" style={{ background: EDGE_COLORS.RELATES_TO }} />
          <span>Relates</span>
        </div>
        <div className="legend-item">
          <span className="legend-line" style={{ background: EDGE_COLORS.CONFLICTS_WITH }} />
          <span>Conflict</span>
        </div>
        <div className="legend-item">
          <span className="legend-line" style={{ background: EDGE_COLORS.ANALOGOUS_TO }} />
          <span>Analogy</span>
        </div>
      </div>

      {/* Context Menu */}
      {contextMenu && (
        <div 
          className="graph-context-menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <div className="context-menu-title">{contextMenu.node.name}</div>
          <button onClick={() => handleCrossDomain(contextMenu.node.name, 'Physics')}>
            <Zap size={12} /> Show in Physics
          </button>
          <button onClick={() => handleCrossDomain(contextMenu.node.name, 'Music Theory')}>
            <Zap size={12} /> Show in Music Theory
          </button>
          <button onClick={() => handleCrossDomain(contextMenu.node.name, 'Biology')}>
            <Zap size={12} /> Show in Biology
          </button>
          <button onClick={() => handleCrossDomain(contextMenu.node.name, 'Economics')}>
            <Zap size={12} /> Show in Economics
          </button>
          <button onClick={() => { setContextMenu(null); }}>
            <AlertTriangle size={12} /> View Conflicts
          </button>
          <button onClick={() => { setContextMenu(null); }}>
            <Clock size={12} /> Timeline
          </button>
        </div>
      )}

      {/* Selected node info */}
      {selectedNode && (
        <div className="graph-node-info">
          <strong>{selectedNode.name}</strong>
          <span>{(selectedNode.labels || []).join(', ')}</span>
          {selectedNode.domain && <span>Domain: {selectedNode.domain}</span>}
          <button className="btn-ghost" onClick={() => setSelectedNode(null)}>×</button>
        </div>
      )}
    </div>
  );
}
