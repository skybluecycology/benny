

interface SidebarTabsProps {
  activeTab: 'flows' | 'sources';
  onTabChange: (tab: 'flows' | 'sources') => void;
}

export default function SidebarTabs({ activeTab, onTabChange }: SidebarTabsProps) {
  return (
    <div style={{
      display: 'flex',
      gap: '4px',
      padding: '8px',
      borderBottom: '1px solid var(--border-color)',
      background: ' var(--surface)'
    }}>
      <button
        className={`btn ${activeTab === 'flows' ? 'btn-gradient' : 'btn-ghost'}`}
        onClick={() => onTabChange('flows')}
        style={{ flex: 1, fontSize: '13px' }}
      >
        Flows
      </button>
      <button
        className={`btn ${activeTab === 'sources' ? 'btn-gradient' : 'btn-ghost'}`}
        onClick={() => onTabChange('sources')}
        style={{ flex: 1, fontSize: '13px' }}
      >
        Sources
      </button>
    </div>
  );
}
