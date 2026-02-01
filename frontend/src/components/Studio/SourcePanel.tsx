import { useState, useEffect, useRef } from 'react';
import { Upload, File, FileText, Trash2, Loader, Check, Download } from 'lucide-react';
import { useWorkspaceStore } from '../../hooks/useWorkspaceStore';

interface SourceFile {
  name: string;
  path: string;
  size: number;
  modified?: number;
}

export default function SourcePanel() {
  const { currentWorkspace } = useWorkspaceStore();
  const [files, setFiles] = useState<SourceFile[]>([]);
  const [activeSources, setActiveSources] = useState<Set<string>>(new Set());
  const [uploading, setUploading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Refresh files when workspace changes
  useEffect(() => {
    fetchFiles();
    setActiveSources(new Set()); // Reset active selection
  }, [currentWorkspace]);

  const fetchFiles = async () => {
    try {
      const response = await fetch(`http://localhost:8000/api/files?workspace=${currentWorkspace}`);
      const data = await response.json();
      setFiles(data.data_in || []);
    } catch (error) {
      console.error('Failed to fetch files:', error);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    
    const files = Array.from(e.dataTransfer.files);
    files.forEach(uploadFile);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    files.forEach(uploadFile);
  };

  const uploadFile = async (file: File) => {
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      await fetch(`http://localhost:8000/api/files/upload?workspace=${currentWorkspace}`, {
        method: 'POST',
        body: formData
      });
      fetchFiles();
    } catch (error) {
      console.error('Upload failed:', error);
    } finally {
      setUploading(false);
    }
  };

  const deleteFile = async (filename: string) => {
    try {
      await fetch(`http://localhost:8000/api/files/${filename}?workspace=${currentWorkspace}`, {
        method: 'DELETE'
      });
      fetchFiles();
      const newActive = new Set(activeSources);
      newActive.delete(filename);
      setActiveSources(newActive);
    } catch (error) {
      console.error('Delete failed:', error);
    }
  };
  
  const downloadFile = async (filename: string) => {
    try {
      const response = await fetch(`http://localhost:8000/api/files/${currentWorkspace}/data_in/${filename}`);
      if (!response.ok) throw new Error('Download failed');
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Download failed:', error);
      alert('Failed to download file');
    }
  };

  const toggleActive = (filename: string) => {
    const newActive = new Set(activeSources);
    if (newActive.has(filename)) {
      newActive.delete(filename);
    } else {
      newActive.add(filename);
    }
    setActiveSources(newActive);
  };

  const ingestFiles = async () => {
    setIngesting(true);
    try {
      await fetch('http://localhost:8000/api/rag/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workspace: currentWorkspace })
      });
      alert('Files indexed successfully!');
    } catch (error) {
      console.error('Ingestion failed:', error);
      alert('Ingestion failed');
    } finally {
      setIngesting(false);
    }
  };

  const getFileIcon = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase();
    if (ext === 'pdf') return <File size={20} style={{ color: '#ef4444' }} />;
    if (ext === 'md') return <FileText size={20} style={{ color: '#3b82f6' }} />;
    return <FileText size={20} style={{ color: '#10b981' }} />;
  };

  return (
    <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '16px', height: '100%' }}>
      {/* Upload Area */}
      <div
        className={`upload-zone ${dragActive ? 'active' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        style={{
          border: `2px dashed ${dragActive ? 'var(--primary)' : 'var(--border-color)'}`,
          borderRadius: '12px',
          padding: '24px',
          textAlign: 'center',
          cursor: 'pointer',
          background: dragActive ? 'rgba(168, 139, 250, 0.1)' : 'var(--surface)',
          transition: 'all 0.2s ease'
        }}
      >
        <Upload size={32} style={{ margin: '0 auto 12px', color: 'var(--text-muted)' }} />
        <div style={{ fontSize: '14px', fontWeight: '500' }}>
          {uploading ? 'Uploading...' : 'Drop files or click to upload'}
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
          PDF, TXT, MD supported
        </div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.txt,.md"
          style={{ display: 'none' }}
          onChange={handleFileSelect}
        />
      </div>

      {/* Source Cards */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {files.length === 0 && (
          <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-muted)', fontSize: '13px' }}>
            No files in workspace "{currentWorkspace}"
          </div>
        )}
        
        {files.map((file) => (
          <div
            key={file.name}
            className="glass-card source-card"
            style={{
              padding: '12px',
              background: activeSources.has(file.name) 
                ? 'linear-gradient(135deg, rgba(168, 139, 250, 0.2), rgba(139, 92, 246, 0.1))'
                : 'var(--surface-elevated)',
              border: activeSources.has(file.name) 
                ? '1px solid var(--primary)' 
                : '1px solid var(--border-color)',
              borderRadius: '10px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              transition: 'all 0.2s ease',
              cursor: 'pointer'
            }}
            onClick={() => toggleActive(file.name)}
          >
            {getFileIcon(file.name)}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: '13px', fontWeight: '500', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {file.name}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                {(file.size / 1024).toFixed(1)} KB
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: '4px' }}>
              <button
                className="btn btn-ghost"
                onClick={(e) => {
                  e.stopPropagation();
                  downloadFile(file.name);
                }}
                style={{ padding: '6px' }}
                title="Download"
              >
                <Download size={14} />
              </button>
              <button
                className="btn btn-ghost"
                onClick={(e) => {
                  e.stopPropagation();
                  deleteFile(file.name);
                }}
                style={{ padding: '6px' }}
                title="Delete"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Ingest Button */}
      <button
        className="btn btn-gradient"
        onClick={ingestFiles}
        disabled={files.length === 0 || ingesting}
        style={{ width: '100%', gap: '8px' }}
      >
        {ingesting ? (
          <>
            <Loader className="animate-spin" size={16} />
            Indexing...
          </>
        ) : (
          <>
            Index {files.length} file{files.length !== 1 ? 's' : ''}
          </>
        )}
      </button>
    </div>
  );
}
