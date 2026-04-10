import { useEffect, useRef, useState, useCallback } from 'react';
import ForceGraph3D from '3d-force-graph';
import { Share2, Zap, Clock, AlertTriangle, RefreshCw, Maximize2, Minimize2, Search } from 'lucide-react';
import { API_BASE_URL } from '../../constants';

interface GraphNode {
  id: string;
  name: string;
  labels: string[];
  domain: string;
  node_type?: string;
  created_at: string;
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
  section?: string;
  citation?: string;
  confidence?: number;
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

// Dynamic color assignments for Entity Typing Category Maps
const NODE_COLORS: Record<string, string> = {
  Concept: '#a56eff',
  Source: '#4dbbff',
  Theory: '#ff9f0a',
  Technology: '#34c759',
  Person: '#ff3b30',
  Organization: '#007aff',
  Event: '#ffcc00',
  Location: '#ff375f'
};

export default function KnowledgeGraphCanvas({ onConceptClick, workspace = 'default' }: KnowledgeGraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] });
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [selectedNode, setSelectedNode] = useState<any | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; node: any } | null>(null);
  const [viewMode, setViewMode] = useState<'graph' | 'map'>('graph');
  
  // Filtering & Isolation States
  const [searchQuery, setSearchQuery] = useState('');
  const focusRef = useRef({ 
    node: null as GraphNode | null, 
    search: '', 
    links: new Set<any>(), 
    neighbors: new Set<string>() 
  });

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    try {
      const timestamp = Date.now();
      const [graphRes, statsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/graph/full?workspace=${workspace}&t=${timestamp}`),
        fetch(`${API_BASE_URL}/api/graph/stats?workspace=${workspace}&t=${timestamp}`)
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

  // Real-time Poll for incremental updates during ingestion
  useEffect(() => {
    let interval: any = null;
    if (loading) {
       interval = setInterval(async () => {
         try {
           const res = await fetch(`${API_BASE_URL}/api/graph/recent?workspace=${workspace}`);
           if (res.ok) {
             const data = await res.json();
             if (data.edges && data.edges.length > 0) {
                // Incremental refresh logic could go here
                // For now, we just fetch the full graph to keep it simple but accurate
                fetchGraph();
             }
           }
         } catch (e) {}
       }, 5000);
    }
    return () => clearInterval(interval);
  }, [loading, workspace, fetchGraph]);

  // Initial load
  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  // Propagate search & select states into the active ref immediately to restyle WebGL dynamically
  useEffect(() => {
    if (!graphRef.current) return;
    
    focusRef.current.search = searchQuery.toLowerCase();
    focusRef.current.node = selectedNode;
    focusRef.current.neighbors.clear();
    focusRef.current.links.clear();

    if (selectedNode) {
      focusRef.current.neighbors.add(selectedNode.id);
      graphData.edges.forEach((edge: any) => {
        if (edge.source.id === selectedNode.id || edge.target.id === selectedNode.id) {
          focusRef.current.neighbors.add(edge.source.id);
          focusRef.current.neighbors.add(edge.target.id);
          focusRef.current.links.add(edge);
        }
      });
    }

    graphRef.current
      .nodeColor(graphRef.current.nodeColor())
      .linkColor(graphRef.current.linkColor())
      .nodeOpacity(graphRef.current.nodeOpacity())
      .linkOpacity(graphRef.current.linkOpacity());
  }, [searchQuery, selectedNode, graphData]);

  // Render 3D force graph
  useEffect(() => {
    if (!containerRef.current || graphData.nodes.length === 0) return;

    if (graphRef.current) {
      graphRef.current._destructor?.();
      containerRef.current.innerHTML = '';
    }

    // Dynamic selection of the constructor to handle ESM/CJS compatibility
    const ForceGraph3D_Lib = (ForceGraph3D as any).default || ForceGraph3D;
    const graph = (ForceGraph3D_Lib)()(containerRef.current)
      .backgroundColor('rgba(0,0,0,0)')
      
      // Node Coloring with Entity Typing
      .nodeColor((node: any) => {
        if (focusRef.current.search && !node.name.toLowerCase().includes(focusRef.current.search)) return '#1f2937';
        if (focusRef.current.node && !focusRef.current.neighbors.has(node.id)) return '#1f2937';
        
        const typeLabel = node.node_type || (node.labels || [])[0] || 'Concept';
        return NODE_COLORS[typeLabel] || NODE_COLORS['Concept'];
      })
      
      // Node Opacity & Highlighting
      .nodeOpacity((node: any) => {
         if (focusRef.current.search && !node.name.toLowerCase().includes(focusRef.current.search)) return 0.1;
         if (focusRef.current.node && !focusRef.current.neighbors.has(node.id)) return 0.1;
         return 0.95;
      })
      
      .nodeLabel((node: any) => {
        const typeLabel = node.node_type || (node.labels || [])[0] || 'Concept';
        return `<div style="background:rgba(15,15,30,0.9);padding:6px 10px;border-radius:6px;color:#e2e8f0;font-size:12px;border:1px solid rgba(139,92,246,0.3)">
          <strong>${node.name}</strong><br/>
          <span style="opacity:0.7">${typeLabel}</span>
        </div>`;
      })
      .nodeVal((node: any) => {
        const baseSize = (node.labels || [])[0] === 'Source' ? 4 : 6;
        // Centrality scaling: Nodes with high centrality grow larger
        const centralityBonus = node.centrality ? Math.log10(node.centrality + 1) * 8 : 0;
        return baseSize + centralityBonus;
      })
      
      // Organic Link Curvature (MindNode style)
      .linkCurvature(0.25)
      .linkCurveRotation(Math.PI / 4)
      
      // Edge Style Logic & Confidence Dampening
      .linkColor((link: any) => {
         if (focusRef.current.node && !focusRef.current.links.has(link)) return '#1f2937';
         return EDGE_COLORS[link.type] || '#4a5568';
      })
      .linkOpacity((link: any) => {
         if (focusRef.current.node && !focusRef.current.links.has(link)) return 0.05;
         const baseOpacity = link.confidence !== undefined ? Math.max(0.2, link.confidence) : 0.6;
         return baseOpacity;
      })
      .linkWidth((link: any) => (focusRef.current.links.has(link) ? 2.5 : 1.2))
      .linkDirectionalArrowLength((link: any) => (focusRef.current.node && !focusRef.current.links.has(link) ? 0 : 4))
      .linkDirectionalArrowRelPos(1)
      .linkDirectionalParticles((link: any) => (focusRef.current.links.has(link) ? 4 : 0))
      .linkDirectionalParticleSpeed(0.01)
      
      // Interactive Citation Hover Details!
      .linkLabel((link: any) => {
        const citationStr = link.citation ? `<div style="margin-top:4px; font-style:italic; font-size:10px; opacity:0.8; max-width:200px; white-space:normal">"${link.citation}"</div>` : '';
        const sectionStr = link.section ? `<div style="margin-top:2px; font-size:9px; color:#a78bfa">${link.section}</div>` : '';
        const confStr = link.confidence !== undefined ? `<div style="margin-top:4px; font-size:9px; color:#10b981">Confidence: ${Math.round(link.confidence * 100)}%</div>` : '';
        
        return `<div style="background:rgba(15,15,30,0.95);padding:6px 10px;border-radius:6px;color:#e2e8f0;font-size:11px;border:1px solid rgba(99,102,241,0.4);max-width:220px">
          <strong>${link.predicate || link.type}</strong>
          ${confStr}
          ${sectionStr}
          ${citationStr}
        </div>`;
      })
      
      .onNodeClick((node: any) => {
        setSelectedNode(node);
        if (onConceptClick) onConceptClick(node.name);
        
        // Dynamic camera zoom into the selected target neighbourhood
        const distance = 150;
        const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z);
        graphRef.current.cameraPosition(
          { x: node.x * distRatio, y: (node.y || 0) * distRatio, z: (node.z || 0) * distRatio },
          node, 1500
        );
      })
      .onNodeRightClick((node: any, event: MouseEvent) => {
        event.preventDefault();
        setContextMenu({ x: event.clientX, y: event.clientY, node: node });
      })
      .onBackgroundClick(() => {
         setSelectedNode(null); // Escape focus isolation clicking the background
      })
      .width(containerRef.current.clientWidth)
      .height(containerRef.current.clientHeight);

    // Map Mode logic: Flatten Z-axis and add continent backgrounds
    if (viewMode === 'map') {
      graph.numDimensions(2); // Perspective becomes 2D-like for the "Atlas" feel
    } else {
      graph.numDimensions(3);
    }

    const links = graphData.edges.map(e => ({ ...e, source: e.source, target: e.target }));

    graph.graphData({
      nodes: graphData.nodes.map(n => ({ ...n })),
      links
    });

    graphRef.current = graph;

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current) {
        graph.width(containerRef.current.clientWidth);
        graph.height(containerRef.current.clientHeight);
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => resizeObserver.disconnect();
  }, [graphData, onConceptClick]);

  const handleCrossDomain = async (concept: string, domain: string) => {
    setContextMenu(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/graph/cross-domain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ concept, target_domain: domain, workspace })
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
      {/* Interactive Toolbar */}
      <div className="graph-toolbar" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <div className="graph-toolbar-left" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Share2 size={14} style={{ color: 'var(--primary)' }} />
          <span className="graph-toolbar-title">Knowledge Graph</span>
          
          <div style={{ marginLeft: '12px', display: 'flex', alignItems: 'center', background: 'rgba(0,0,0,0.15)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '2px 8px' }}>
             <Search size={12} style={{ opacity: 0.5, marginRight: '6px' }} />
             <input 
               type="text" 
               placeholder="Search cluster..." 
               value={searchQuery}
               onChange={(e) => setSearchQuery(e.target.value)}
               style={{ background: 'transparent', border: 'none', color: 'var(--text-primary)', fontSize: '11px', outline: 'none', width: '120px' }}
             />
          </div>
          
          {stats && (
            <span className="graph-toolbar-stats" style={{ marginLeft: '8px' }}>
              {stats.concepts} concepts · {stats.relationships} relations
            </span>
          )}
        </div>
        <div className="graph-toolbar-right" style={{ display: 'flex', gap: '8px' }}>
          {/* View Toggle Pill */}
          <div style={{ display: 'flex', background: 'rgba(0,0,0,0.2)', borderRadius: 'var(--radius-pill)', padding: '4px', border: '1px solid var(--border-color)', marginRight: '8px' }}>
            <button 
              onClick={() => setViewMode('graph')}
              style={{
                padding: '4px 12px',
                borderRadius: 'var(--radius-pill)',
                border: 'none',
                background: viewMode === 'graph' ? 'var(--branch-purple)' : 'transparent',
                color: viewMode === 'graph' ? '#fff' : 'var(--text-muted)',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              Graph
            </button>
            <button 
              onClick={() => setViewMode('map')}
              style={{
                padding: '4px 12px',
                borderRadius: 'var(--radius-pill)',
                border: 'none',
                background: viewMode === 'map' ? 'var(--branch-teal)' : 'transparent',
                color: viewMode === 'map' ? '#fff' : 'var(--text-muted)',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              Map
            </button>
          </div>

          <button className="btn-icon btn-ghost" onClick={fetchGraph} title="Refresh">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          <button className="btn-icon btn-ghost" onClick={() => setIsFullscreen(!isFullscreen)} title="Toggle Fullscreen">
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      <div ref={containerRef} className="graph-3d-container" onClick={() => setContextMenu(null)} />

      {graphData.nodes.length === 0 && !loading && (
        <div className="graph-empty-state">
          <Share2 size={32} style={{ opacity: 0.4 }} />
          <p>No knowledge graph yet</p>
          <span>Ingest text to build the relational graph</span>
        </div>
      )}

      {/* Semantic Legend */}
      <div className="graph-legend" style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', maxWidth: '400px' }}>
        {Object.entries(NODE_COLORS).map(([type, color]) => (
           <div key={type} className="legend-item" style={{ cursor: 'pointer' }} onClick={() => setSearchQuery(searchQuery === type ? '' : type)}>
             <span className="legend-dot" style={{ background: color }} />
             <span style={{ opacity: searchQuery && searchQuery !== type.toLowerCase() ? 0.5 : 1 }}>{type}</span>
           </div>
        ))}
      </div>

      {contextMenu && (
        <div className="graph-context-menu" style={{ left: contextMenu.x, top: contextMenu.y }}>
          <div className="context-menu-title">{contextMenu.node.name}</div>
          <button onClick={() => handleCrossDomain(contextMenu.node.name, 'Physics')}><Zap size={12} /> Show in Physics</button>
          <button onClick={() => handleCrossDomain(contextMenu.node.name, 'Biology')}><Zap size={12} /> Show in Biology</button>
          <button onClick={() => handleCrossDomain(contextMenu.node.name, 'Economics')}><Zap size={12} /> Show in Economics</button>
          <button onClick={() => setContextMenu(null)}><AlertTriangle size={12} /> View Conflicts</button>
        </div>
      )}

      {selectedNode && (
        <div className="graph-node-info" style={{ background: 'rgba(15, 15, 20, 0.95)', border: '1px solid var(--border-color)', backdropFilter: 'blur(8px)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
             <strong style={{ fontSize: '14px', color: 'var(--primary)' }}>{selectedNode.name}</strong>
             <button className="btn-ghost" onClick={() => setSelectedNode(null)}>×</button>
          </div>
          <span style={{ background: 'rgba(139,92,246,0.1)', padding: '2px 6px', borderRadius: '4px', fontSize: '11px', color: '#a78bfa', display: 'inline-block', marginBottom: '4px' }}>
             {selectedNode.node_type || (selectedNode.labels || [])[0] || 'Concept'}
          </span>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
             <em>Sub-graph isolated. Click background to reset visualization.</em>
          </div>
        </div>
      )}
    </div>
  );
}
