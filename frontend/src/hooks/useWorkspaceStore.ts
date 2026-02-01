import { create } from 'zustand';

interface WorkspaceState {
  currentWorkspace: string;
  workspaces: string[];
  fetchWorkspaces: () => Promise<void>;
  createWorkspace: (name: string) => Promise<boolean>;
  setCurrentWorkspace: (workspace: string) => void;
  activeLLMProvider: string;
  setActiveLLMProvider: (provider: string) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  currentWorkspace: 'default',
  workspaces: ['default'],

  fetchWorkspaces: async () => {
    try {
      const response = await fetch('http://localhost:8000/api/workspaces');
      if (response.ok) {
        const data = await response.json();
        // Assuming data is { workspaces: string[] } or just string[]
        // API returns list_workspaces() which is usually string[]
        const workspaceList = Array.isArray(data) ? data : (data.workspaces || []);
        
        // Ensure default is always there
        if (!workspaceList.includes('default')) {
          workspaceList.unshift('default');
        }
        
        set({ workspaces: workspaceList });
      }
    } catch (error) {
      console.error('Failed to fetch workspaces:', error);
    }
  },

  createWorkspace: async (name: string) => {
    try {
      const response = await fetch(`http://localhost:8000/api/workspaces/${name}`, {
        method: 'POST'
      });
      
      if (response.ok) {
        await get().fetchWorkspaces();
        set({ currentWorkspace: name });
        return true;
      }
      return false;
    } catch (error) {
      console.error('Failed to create workspace:', error);
      return false;
    }
  },

  setCurrentWorkspace: (workspace: string) => {
    set({ currentWorkspace: workspace });
  },

  activeLLMProvider: 'fastflowlm',
  setActiveLLMProvider: (provider: string) => {
    set({ activeLLMProvider: provider });
  }
}));
