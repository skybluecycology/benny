import React, { useState, useEffect } from 'react';
import { Activity, Shield, Terminal, HardDrive, RefreshCw, AlertTriangle, CheckCircle2, Clock } from 'lucide-react';
import { GOVERNANCE_HEADERS } from '../../constants';

interface Task {
  task_id: string;
  workspace: string;
  type: string;
  status: string;
  progress: number;
  message: string;
  aer_log: any[];
  updated_at: string;
}

const GlobalAdminDashboard: React.FC = () => {
    const [tasks, setTasks] = useState<Task[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    const fetchTasks = async () => {
        try {
            // Cognitive Mesh: Secure governance call with X-Benny-API-Key
            const response = await fetch('/api/tasks', {
                headers: { ...GOVERNANCE_HEADERS }
            });
            if (!response.ok) throw new Error('Auth failed');
            const data = await response.json();
            setTasks(Array.isArray(data) ? data : []);
        } catch (error) {
            console.error('Failed to fetch tasks:', error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchTasks();
        const interval = setInterval(fetchTasks, 5000); // Mesh heartbeat
        return () => clearInterval(interval);
    }, []);

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'completed': return <CheckCircle2 className="text-green-500" size={16} />;
            case 'running': return <RefreshCw className="text-blue-500 animate-spin" size={16} />;
            case 'failed': return <AlertTriangle className="text-red-500" size={16} />;
            default: return <Clock className="text-gray-400" size={16} />;
        }
    };

    return (
        <div className="admin-dashboard p-6 overflow-auto h-full bg-surface-darker">
            <header className="mb-8 border-b border-border pb-4 flex justify-between items-end">
                <div>
                   <h1 className="text-2xl font-bold flex items-center gap-2 text-white">
                        <Shield className="text-primary" /> Mesh Governance Console
                    </h1>
                    <p className="text-secondary text-sm mt-1">Real-time oversight of Cognitive Mesh task orchestration and security.</p>
                </div>
                <div className="text-[10px] text-gray-500 font-mono">NODE_UID: {window.location.hostname}</div>
            </header>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div className="card-glass p-4 border border-white/5 rounded-xl bg-white/5">
                    <div className="flex items-center gap-2 text-primary mb-2">
                        <Activity size={18} />
                        <span className="font-semibold text-xs tracking-wider uppercase">Active Mesh Flux</span>
                    </div>
                    <div className="text-3xl font-bold text-white">{tasks.filter(t => t.status === 'running').length}</div>
                    <div className="text-[10px] text-secondary mt-1">Parallel reasoning threads</div>
                </div>
                <div className="card-glass p-4 border border-white/5 rounded-xl bg-white/5">
                    <div className="flex items-center gap-2 text-green-500 mb-2">
                        <CheckCircle2 size={18} />
                        <span className="font-semibold text-xs tracking-wider uppercase">Governance Score</span>
                    </div>
                    <div className="text-3xl font-bold text-white">98%</div>
                    <div className="text-[10px] text-secondary mt-1">Compliance with Metadata Facets</div>
                </div>
                <div className="card-glass p-4 border border-white/5 rounded-xl bg-white/5">
                    <div className="flex items-center gap-2 text-blue-500 mb-2">
                        <HardDrive size={18} />
                        <span className="font-semibold text-xs tracking-wider uppercase">Provenance Persistence</span>
                    </div>
                    <div className="text-3xl font-bold text-white">{tasks.length}</div>
                    <div className="text-[10px] text-secondary mt-1">Total run records in vault</div>
                </div>
            </div>

            <div className="card-glass overflow-hidden border border-white/10 rounded-xl bg-white/5">
                <div className="p-4 border-b border-white/10 bg-black/20 flex justify-between items-center text-white">
                    <h3 className="font-semibold text-sm flex items-center gap-2">
                        <Terminal size={14} /> Global Task Registry
                    </h3>
                    <div className="flex items-center gap-4">
                        <span className="text-[10px] text-secondary">Updates every 5s</span>
                        <button onClick={fetchTasks} className="btn-icon btn-ghost p-1 hover:text-primary">
                            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
                        </button>
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm text-gray-300">
                        <thead>
                            <tr className="bg-white/5 border-b border-white/10">
                                <th className="p-3 text-[10px] uppercase tracking-widest text-secondary">Type</th>
                                <th className="p-3 text-[10px] uppercase tracking-widest text-secondary">Task ID</th>
                                <th className="p-3 text-[10px] uppercase tracking-widest text-secondary">Workspace</th>
                                <th className="p-3 text-[10px] uppercase tracking-widest text-secondary">Telemetry</th>
                                <th className="p-3 text-[10px] uppercase tracking-widest text-secondary">Status</th>
                                <th className="p-3 text-[10px] uppercase tracking-widest text-secondary">AER Provenance</th>
                            </tr>
                        </thead>
                        <tbody>
                            {tasks.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="p-12 text-center text-secondary italic">
                                        Vault is currently quiet. No Mesh activity recorded.
                                    </td>
                                </tr>
                            ) : tasks.slice().reverse().map(task => (
                                <tr key={task.task_id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                                    <td className="p-3">
                                        <span className="px-2 py-0.5 bg-primary/10 text-primary border border-primary/20 rounded text-[9px] uppercase font-bold">
                                            {task.type.replace('_', ' ')}
                                        </span>
                                    </td>
                                    <td className="p-3 text-xs font-mono text-gray-400">{task.task_id.slice(0, 8)}</td>
                                    <td className="p-3 font-medium">{task.workspace}</td>
                                    <td className="p-3 min-w-[180px]">
                                        <div className="w-full bg-white/10 rounded-full h-1 mb-1.5 overflow-hidden">
                                            <div 
                                                className="bg-gradient-to-r from-primary to-blue-400 h-1 rounded-full transition-all duration-700 ease-out" 
                                                style={{ width: `${task.progress}%` }}
                                            />
                                        </div>
                                        <div className="text-[10px] text-gray-500 flex justify-between">
                                            <span>{task.message}</span>
                                            <span className="font-mono">{task.progress}%</span>
                                        </div>
                                    </td>
                                    <td className="p-3">
                                        <div className="flex items-center gap-2 text-xs">
                                            {getStatusIcon(task.status)}
                                            <span className="capitalize">{task.status}</span>
                                        </div>
                                    </td>
                                    <td className="p-3">
                                        <div className="flex items-center gap-1 text-primary text-[10px] cursor-pointer hover:underline bg-primary/5 px-2 py-1 rounded inline-flex">
                                            <Terminal size={10} /> {task.aer_log.length} AER frames
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            <footer className="mt-8 text-center">
                <div className="inline-flex items-center gap-1.5 text-[10px] text-gray-600 uppercase tracking-tighter">
                   <Shield size={10} /> Benny Mesh Governance Protocol v1.4 // Hard Gate Enforcement Active
                </div>
            </footer>
        </div>
    );
};

export default GlobalAdminDashboard;
