import { useState, useEffect, useRef } from 'react';
import { Upload, File, FileText, Trash2, Loader, Download, Terminal, Link, Book } from 'lucide-react';
import { useWorkspaceStore } from '../../hooks/useWorkspaceStore';

interface SourceFile {
  name: string;
  path: string;
  size: number;
  modified?: number;
}

export default function DataManagementPanel() {
  const { currentWorkspace, setActiveDocument, selectedDocuments, toggleSelectedDocument } = useWorkspaceStore();
  const [inFiles, setInFiles] = useState<SourceFile[]>([]);
  const [outFiles, setOutFiles] = useState<SourceFile[]>([]);
  const [indexedFiles, setIndexedFiles] = useState<string[]>([]);
  const [activeSources, setActiveSources] = useState<Set<string>>(new Set());
  const [uploading, setUploading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [ingestLogs, setIngestLogs] = useState<string[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Poll for logs when ingesting or when showLogs is true
  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (ingesting || showLogs) {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`http://localhost:8005/api/rag/logs?workspace=${currentWorkspace}`);
          const data = await res.json();
          setIngestLogs(data.logs || []);
          logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        } catch (e) {
          console.error('Failed to fetch logs', e);
        }
      }, 1000);
    } else {
      setIngestLogs([]);
    }
    return () => clearInterval(interval);
  }, [ingesting, showLogs, currentWorkspace]);

  // Refresh files when workspace changes
  useEffect(() => {
    fetchFiles();
    fetchIndexedStatus();
    setActiveSources(new Set()); // Reset active selection
  }, [currentWorkspace]);

  const fetchIndexedStatus = async () => {
    try {
      const response = await fetch(`http://localhost:8005/api/rag/status?workspace=${currentWorkspace}`);
      if (!response.ok) return;
      const data = await response.json();
      setIndexedFiles(data.sources || []);
    } catch (error) {
       console.error('Failed to fetch indexed status:', error);
    }
  };

  const fetchFiles = async () => {
    try {
      const response = await fetch(`http://localhost:8005/api/files?workspace=${currentWorkspace}`);
      const data = await response.json();
      setInFiles(data.data_in || []);
      setOutFiles(data.data_out || []);
    } catch (error) {
      console.error('Failed to fetch files:', error);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const files = Array.from(e.dataTransfer.files);
    await processAndUploadFiles(files);
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    await processAndUploadFiles(files);
  };

  const processAndUploadFiles = async (files: File[]) => {
    if (files.length === 0) return;

    const shouldIndex = window.confirm(
      `You are uploading ${files.length} document(s).\n\nWould you like to automatically index them for the AI agent now?\n\n(Note: This offloads the indexing process to the background, and will automatically perform OCR on scanned PDFs).`
    );

    setUploading(true);
    let uploadedCurrent = [];

    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        await fetch(`http://localhost:8005/api/files/upload?workspace=${currentWorkspace}`, {
          method: 'POST',
          body: formData
        });
        uploadedCurrent.push(file.name);
      } catch (error) {
        console.error('Upload failed:', error);
      }
    }

    await fetchFiles();
    setUploading(false);

    if (shouldIndex && uploadedCurrent.length > 0) {
      setIngesting(true);
      try {
        await fetch('http://localhost:8005/api/rag/ingest', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            workspace: currentWorkspace,
            files: uploadedCurrent
          })
        });
        alert('Files uploaded and indexed successfully!');
      } catch (error) {
        console.error('Ingestion failed:', error);
        alert('Upload succeeded, but ingestion failed. You can retry indexing manually.');
      } finally {
        setIngesting(false);
      }
    }
  };

  const deleteFile = async (filename: string, subdir: string) => {
    try {
      await fetch(`http://localhost:8005/api/files/${filename}?workspace=${currentWorkspace}&subdir=${subdir}`, {
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

  const importFromUrl = async () => {
    const url = window.prompt("Enter the URL to import (e.g. Gutenberg Book HTML URL):");
    if (!url) return;

    setUploading(true);
    let uploadedFile = null;
    try {
      const res = await fetch(`http://localhost:8005/api/files/download-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, workspace: currentWorkspace })
      });
      if (!res.ok) throw new Error("Download failed");
      const data = await res.json();
      uploadedFile = data.filename;
    } catch (e: any) {
      console.error(e);
      alert("Failed to download from URL: " + e.message);
    }
    setUploading(false);
    await fetchFiles();

    if (uploadedFile) {
      const shouldIndex = window.confirm(`Successfully imported ${uploadedFile}. Would you like to index it for the AI agent now?`);
      if (shouldIndex) {
        setIngesting(true);
        try {
          await fetch('http://localhost:8005/api/rag/ingest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
              workspace: currentWorkspace,
              files: [uploadedFile]
            })
          });
          alert('File imported and indexed successfully!');
        } catch (error) {
          console.error('Ingestion failed:', error);
          alert('Import succeeded, but ingestion failed. You can retry indexing manually.');
        } finally {
          setIngesting(false);
        }
      }
    }
  };

  const importFromGutenberg = async () => {
    const url = window.prompt("Enter the Gutenberg Book TXT URL to import (e.g. .../pg76432.txt):");
    if (!url) return;

    setUploading(true);
    let uploadedFile = null;
    try {
      const res = await fetch(`http://localhost:8005/api/files/download-gutenberg`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, workspace: currentWorkspace })
      });
      if (!res.ok) throw new Error("Download failed");
      const data = await res.json();
      uploadedFile = data.filename;
    } catch (e: any) {
      console.error(e);
      alert("Failed to download from Gutenberg: " + e.message);
    }
    setUploading(false);
    await fetchFiles();

    if (uploadedFile) {
      const shouldIndex = window.confirm(`Successfully imported Gutenberg Book as ${uploadedFile}. Would you like to index it for the AI agent now?`);
      if (shouldIndex) {
        setIngesting(true);
        try {
          await fetch('http://localhost:8005/api/rag/ingest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
              workspace: currentWorkspace,
              files: [uploadedFile]
            })
          });
          alert('Gutenberg Book imported and indexed successfully!');
        } catch (error) {
          console.error('Ingestion failed:', error);
          alert('Import succeeded, but ingestion failed. You can retry indexing manually.');
        } finally {
          setIngesting(false);
        }
      }
    }
  };
  
  const downloadFile = async (filename: string, subdir: string) => {
    try {
      const response = await fetch(`http://localhost:8005/api/files/${currentWorkspace}/${subdir}/${filename}`);
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
      await fetch('http://localhost:8005/api/rag/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workspace: currentWorkspace })
      });
      alert('Files indexed successfully!');
      fetchIndexedStatus();
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
      
      <div style={{ display: 'flex', gap: '8px', width: '100%' }}>
        <button
          className="btn btn-outline"
          onClick={importFromGutenberg}
          disabled={uploading || ingesting}
          style={{ flex: 1, gap: '8px', justifyContent: 'center' }}
        >
          <Book size={16} />
          Gutenberg TXT
        </button>
        <button
          className="btn btn-outline"
          onClick={importFromUrl}
          disabled={uploading || ingesting}
          style={{ flex: 1, gap: '8px', justifyContent: 'center' }}
        >
          <Link size={16} />
          URL Download
        </button>
      </div>

      {/* Source Cards - Split View */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        
        {/* Workspace Files (data_in) */}
        <div>
          <div style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px', paddingLeft: '4px' }}>
            Workspace Files (data_in)
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {inFiles.length === 0 && (
              <div style={{ textAlign: 'center', padding: '10px', color: 'var(--text-muted)', fontSize: '13px' }}>
                No input files in "{currentWorkspace}"
              </div>
            )}
            
            {inFiles.map((file: SourceFile) => {
              const isIndexed = indexedFiles.includes(file.name);
              const isSelected = selectedDocuments.includes(file.name);
              return (
                <div
                  key={`in-${file.name}`}
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
                  onClick={() => {
                    toggleActive(file.name);
                    setActiveDocument({ name: file.name, subdir: 'data_in' });
                  }}
                >
                  <input 
                    type="checkbox" 
                    checked={isSelected}
                    onChange={() => {}}
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleSelectedDocument(file.name);
                    }}
                    style={{ cursor: 'pointer', width: '16px', height: '16px', accentColor: 'var(--primary)' }}
                    title="Select document as context for Notebook chat"
                    disabled={!isIndexed}
                  />
                  {getFileIcon(file.name)}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <div style={{ fontSize: '13px', fontWeight: '500', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {file.name}
                      </div>
                      {isIndexed && (
                        <div style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#10b981', fontSize: '10px', padding: '2px 6px', borderRadius: '4px', fontWeight: '600' }}>
                          ✓ Indexed
                        </div>
                      )}
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
                        downloadFile(file.name, "data_in");
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
                        deleteFile(file.name, "data_in");
                      }}
                      style={{ padding: '6px' }}
                      title="Delete"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Generated Files (data_out) */}
        <div>
          <div style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px', paddingLeft: '4px' }}>
            Generated Files (data_out)
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {outFiles.length === 0 && (
              <div style={{ textAlign: 'center', padding: '10px', color: 'var(--text-muted)', fontSize: '13px' }}>
                No generated files yet
              </div>
            )}
            
            {outFiles.map((file: SourceFile) => (
              <div
                key={`out-${file.name}`}
                className="glass-card source-card"
                style={{
                  padding: '12px',
                  background: 'var(--surface-elevated)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '10px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                }}
                onClick={() => setActiveDocument({ name: file.name, subdir: 'data_out' })}
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
                    onClick={() => downloadFile(file.name, "data_out")}
                    style={{ padding: '6px' }}
                    title="Download"
                  >
                    <Download size={14} />
                  </button>
                  <button
                    className="btn btn-ghost"
                    onClick={() => deleteFile(file.name, "data_out")}
                    style={{ padding: '6px' }}
                    title="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Ingest Button and Logs */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            className="btn btn-gradient"
            onClick={ingestFiles}
            disabled={activeSources.size === 0 || ingesting}
            style={{ flex: 1, gap: '8px' }}
          >
            {ingesting ? (
              <>
                <Loader className="animate-spin" size={16} />
                Indexing in background...
              </>
            ) : (
              <>
                Index {activeSources.size} file{activeSources.size !== 1 ? 's' : ''}
              </>
            )}
          </button>

          <button
            className="btn btn-outline"
            onClick={() => setShowLogs(!showLogs)}
            style={{ padding: '8px', background: showLogs ? 'var(--surface-elevated)' : 'transparent' }}
            title="Toggle Ingestion Logs"
          >
            <Terminal size={20} />
          </button>
        </div>

        {(ingesting || showLogs) && (
          <div style={{
            background: '#1e1e1e',
            color: '#00ff00',
            fontFamily: 'monospace',
            fontSize: '11px',
            padding: '12px',
            borderRadius: '8px',
            maxHeight: '150px',
            overflowY: 'auto',
            border: '1px solid #333'
          }}>
            {ingestLogs.length === 0 ? "Starting..." : ingestLogs.map((log: string, i: number) => (
              <div key={i}>{log}</div>
            ))}
            <div ref={logsEndRef} />
          </div>
        )}
      </div>
    </div>
  );
}
