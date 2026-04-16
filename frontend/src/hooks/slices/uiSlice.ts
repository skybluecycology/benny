export type UIVersion = 'v1' | 'v2';
export type ViewMode = 'swarm' | 'knowledge' | 'marketplace' | 'llm' | 'graph' | 'documents';

export interface UISlice {
  isAuditHubOpen: boolean;
  isWikiHubOpen: boolean;
  activeWikiConcept: string | null;
  uiVersion: UIVersion;
  playbackIndex: number | null;
  viewMode: ViewMode;
  codeGraph: { nodes: any[], edges: any[] } | null;
  isCodeGraphScanOpen: boolean;
  isGraphManagerOpen: boolean;
  
  // Graph Control State
  selectionTier: 1 | 2 | 3;
  synthesisMode: 'structural' | 'architectural' | 'neural';
  syncMode: 'real_time' | 'streaming' | 'stabilized';
  visibleTypes: string[];
  visibleEdgeTypes: string[];
  showClusters: boolean;

  setAuditHubOpen: (isOpen: boolean) => void;
  toggleAuditHub: () => void;
  setWikiHubOpen: (isOpen: boolean) => void;
  setActiveWikiConcept: (concept: string | null) => void;
  setUIVersion: (version: UIVersion) => void;
  toggleUIVersion: () => void;
  setPlaybackIndex: (index: number | null) => void;
  setViewMode: (mode: ViewMode) => void;
  setCodeGraph: (graph: { nodes: any[], edges: any[] } | null) => void;
  setIsCodeGraphScanOpen: (isOpen: boolean) => void;
  setIsGraphManagerOpen: (isOpen: boolean) => void;
  
  // Graph Control Actions
  setSelectionTier: (tier: 1 | 2 | 3) => void;
  setSynthesisMode: (mode: 'structural' | 'architectural' | 'neural') => void;
  setSyncMode: (mode: 'real_time' | 'streaming' | 'stabilized') => void;
  setVisibleTypes: (types: string[]) => void;
  setVisibleEdgeTypes: (types: string[]) => void;
  toggleShowClusters: () => void;
}

export const createUISlice = (set: any, get: any): UISlice => ({
  isAuditHubOpen: false,
  isWikiHubOpen: false,
  activeWikiConcept: null,
  uiVersion: 'v2',
  playbackIndex: null,
  viewMode: 'swarm',
  codeGraph: null,
  isCodeGraphScanOpen: false,
  isGraphManagerOpen: false,
  
  // Default Graph State
  selectionTier: 1,
  synthesisMode: 'neural',
  syncMode: 'streaming',
  visibleTypes: ['Folder', 'File', 'Class', 'Interface', 'Function', 'Documentation', 'Concept'],
  visibleEdgeTypes: ['DEFINES', 'INHERITS', 'DEPENDS_ON', 'CALLS', 'CONTAINS', 'REL'],
  showClusters: false,

  setAuditHubOpen: (isOpen) => set({ isAuditHubOpen: isOpen }),
  toggleAuditHub: () => set({ isAuditHubOpen: !get().isAuditHubOpen }),
  setWikiHubOpen: (isOpen) => set({ isWikiHubOpen: isOpen }),
  setActiveWikiConcept: (concept) => set({ activeWikiConcept: concept }),
  setUIVersion: (version) => set({ uiVersion: version }),
  toggleUIVersion: () => set({ uiVersion: get().uiVersion === 'v1' ? 'v2' : 'v1' }),
  setPlaybackIndex: (index) => set({ playbackIndex: index }),
  setViewMode: (mode) => set({ viewMode: mode }),
  setCodeGraph: (graph) => set({ codeGraph: graph }),
  setIsCodeGraphScanOpen: (isOpen) => set({ isCodeGraphScanOpen: isOpen }),
  setIsGraphManagerOpen: (isOpen) => set({ isGraphManagerOpen: isOpen }),

  setSelectionTier: (tier) => set({ selectionTier: tier }),
  setSynthesisMode: (mode) => set({ synthesisMode: mode }),
  setSyncMode: (mode) => set({ syncMode: mode }),
  setVisibleTypes: (types) => set({ visibleTypes: types }),
  setVisibleEdgeTypes: (types) => set({ visibleEdgeTypes: types }),
  toggleShowClusters: () => set({ showClusters: !get().showClusters }),
});
