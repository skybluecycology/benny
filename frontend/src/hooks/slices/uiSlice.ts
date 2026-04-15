export type UIVersion = 'v1' | 'v2';
export type ViewMode = 'swarm' | 'knowledge' | 'marketplace' | 'llm' | 'graph' | 'documents';

export interface UISlice {
  isAuditHubOpen: boolean;
  uiVersion: UIVersion;
  playbackIndex: number | null;
  viewMode: ViewMode;
  codeGraph: { nodes: any[], edges: any[] } | null;
  isCodeGraphScanOpen: boolean;
  isGraphManagerOpen: boolean;

  setAuditHubOpen: (isOpen: boolean) => void;
  toggleAuditHub: () => void;
  setUIVersion: (version: UIVersion) => void;
  toggleUIVersion: () => void;
  setPlaybackIndex: (index: number | null) => void;
  setViewMode: (mode: ViewMode) => void;
  setCodeGraph: (graph: { nodes: any[], edges: any[] } | null) => void;
  setIsCodeGraphScanOpen: (isOpen: boolean) => void;
  setIsGraphManagerOpen: (isOpen: boolean) => void;
}

export const createUISlice = (set: any, get: any): UISlice => ({
  isAuditHubOpen: false,
  uiVersion: 'v2',
  playbackIndex: null,
  viewMode: 'swarm',
  codeGraph: null,
  isCodeGraphScanOpen: false,
  isGraphManagerOpen: false,

  setAuditHubOpen: (isOpen) => set({ isAuditHubOpen: isOpen }),
  toggleAuditHub: () => set({ isAuditHubOpen: !get().isAuditHubOpen }),
  setUIVersion: (version) => set({ uiVersion: version }),
  toggleUIVersion: () => set({ uiVersion: get().uiVersion === 'v1' ? 'v2' : 'v1' }),
  setPlaybackIndex: (index) => set({ playbackIndex: index }),
  setViewMode: (mode) => set({ viewMode: mode }),
  setCodeGraph: (graph) => set({ codeGraph: graph }),
  setIsCodeGraphScanOpen: (isOpen) => set({ isCodeGraphScanOpen: isOpen }),
  setIsGraphManagerOpen: (isOpen) => set({ isGraphManagerOpen: isOpen }),
});
