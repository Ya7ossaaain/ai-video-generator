import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring } from 'remotion';

export interface AnchorPoint {
  frame: number;
  x: number;
  y: number;
}

export interface HudOverlayProps {
  modelName?: string;
  highlightPart?: string;
  arabicTitle?: string;
  anchors?: AnchorPoint[];
  durationInFrames?: number;
}

export const HudOverlay: React.FC<HudOverlayProps> = ({
  modelName = 'BOEING 727-100 // FORENSIC WIREFRAME',
  highlightPart = 'VENTRAL AFT AIRSTAIRS',
  arabicTitle = 'تحليل البنية الهندسية ونقطة القفز الخلفية',
  anchors = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const activeAnchor = anchors.length > 0 ? anchors[Math.min(frame, anchors.length - 1)] : { x: 960, y: 540 };
  const lineProgress = spring({ frame, fps, config: { damping: 16 } });

  return (
    <AbsoluteFill style={{ backgroundColor: 'transparent', fontFamily: "'Noto Sans Arabic', monospace, sans-serif" }}>
      <svg width="1920" height="1080" viewBox="0 0 1920 1080" style={{ position: 'absolute', inset: 0 }}>
        <circle cx={activeAnchor.x} cy={activeAnchor.y} r={8} fill="#E52521" />
        <line x1={activeAnchor.x} y1={activeAnchor.y} x2={1240} y2={300} stroke="#FFFFFF" strokeWidth={2 * lineProgress} />
      </svg>
      <div style={{ position: 'absolute', left: 1240, top: 260, width: 460, background: 'rgba(7,10,15,0.9)', border: '1.5px solid #FFF', borderRight: '5px solid #E52521', padding: '16px 22px', direction: 'rtl' }}>
        <div style={{ fontFamily: 'monospace', fontSize: 14, color: '#E52521', direction: 'ltr' }}>{modelName} // {highlightPart}</div>
        <div style={{ fontSize: 22, fontWeight: 800, color: '#FFF', marginTop: 6 }}>{arabicTitle}</div>
      </div>
    </AbsoluteFill>
  );
};
