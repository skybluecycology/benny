import React, { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { GripHorizontal, X } from 'lucide-react';

interface DynamicOverlayProps {
  children: React.ReactNode;
  title: string;
  defaultPosition?: { x: number; y: number };
  defaultSize?: { width: number | string; height: number | string };
  minSize?: { width: number; height: number };
  onClose?: () => void;
  className?: string;
  id?: string;
}

export function DynamicOverlay({ 
  children, 
  title, 
  defaultPosition = { x: 0, y: 0 }, 
  defaultSize = { width: 400, height: 300 },
  minSize = { width: 250, height: 150 },
  onClose,
  className = "",
  id
}: DynamicOverlayProps) {
  const [size, setSize] = useState(defaultSize);
  const [isResizing, setIsResizing] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Custom Resize Logic
  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizing(true);

    const startX = e.clientX;
    const startY = e.clientY;
    const startWidth = containerRef.current?.offsetWidth || 0;
    const startHeight = containerRef.current?.offsetHeight || 0;

    const onMouseMove = (moveEvent: MouseEvent) => {
      const newWidth = Math.max(minSize.width, startWidth + (moveEvent.clientX - startX));
      const newHeight = Math.max(minSize.height, startHeight + (moveEvent.clientY - startY));
      setSize({ width: newWidth, height: newHeight });
    };

    const onMouseUp = () => {
      setIsResizing(false);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  return (
    <motion.div
      ref={containerRef}
      drag
      dragMomentum={false}
      dragListener={!isResizing}
      dragControls={undefined}
      initial={{ ...defaultPosition, opacity: 0 }}
      animate={{ opacity: 1 }}
      style={{
        width: size.width,
        height: size.height,
        position: 'absolute',
        zIndex: 100,
      }}
      className={`glass-panel p-0 flex flex-col overflow-hidden pointer-events-auto border-[#00FFFF]/20 shadow-[0_0_40px_rgba(0,0,0,0.5)] ${className}`}
      id={id}
    >
      {/* Drag & Header Handle */}
      <div className="h-10 px-4 flex justify-between items-center bg-white/5 border-b border-[#00FFFF]/10 cursor-grab active:cursor-grabbing select-none group">
        <div className="flex items-center gap-3">
          <GripHorizontal size={14} className="text-[#00FFFF]/40 group-hover:text-[#00FFFF] transition-colors" />
          <span className="text-[10px] font-black tracking-[0.2em] text-[#00FFFF]/60 uppercase">
            {title}
          </span>
        </div>
        {onClose && (
          <button 
            onClick={onClose}
            className="text-white/20 hover:text-[#FF5F1F] transition-colors p-1"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Pane Content */}
      <div className="flex-1 overflow-hidden relative">
        {children}
      </div>

      {/* Resize Handle (Bottom-Right) */}
      <div 
        onMouseDown={handleResizeStart}
        className="absolute bottom-0 right-0 w-6 h-6 cursor-nwse-resize group/resize z-[110]"
      >
        <div className="absolute bottom-1 right-1 w-3 h-3 border-r-2 border-b-2 border-[#00FFFF]/20 group-hover/resize:border-[#00FFFF] transition-colors" />
      </div>
    </motion.div>
  );
}
