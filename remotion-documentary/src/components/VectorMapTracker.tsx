import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from 'remotion';

export interface Waypoint {
  label: string;
  subLabel?: string;
  x: number;
  y: number;
}

export interface VectorMapTrackerProps {
  title?: string;
  arabicTitle?: string;
  coordinates?: string;
  sectorCode?: string;
  waypoints?: Waypoint[];
  searchZonePolygon?: Array<{ x: number; y: number }>;
  durationInFrames?: number;
}

export const VectorMapTracker: React.FC<VectorMapTrackerProps> = ({
  title = 'FLIGHT 305 // VECTOR TRAJECTORY & SEARCH SECTOR',
  arabicTitle = 'تحليل المسار الجغرافي ومنطقة البحث الجنائي',
  coordinates = '45.9214° N, 122.2819° W',
  sectorCode = 'GIS-SECTOR // PNW-305',
  waypoints = [
    { label: 'PORTLAND (PDX)', subLabel: '14:50 PST // DEPARTURE', x: 520, y: 780 },
    { label: 'LAKE MERWIN DROP ZONE', subLabel: '20:13 PST // AFT STAIRS DEPLOYED', x: 760, y: 510 },
    { label: 'SEATTLE (SEA-TAC)', subLabel: '20:05 PST // LANDING VECTOR', x: 980, y: 240 },
  ],
  searchZonePolygon = [
    { x: 640, y: 440 },
    { x: 890, y: 420 },
    { x: 920, y: 590 },
    { x: 670, y: 610 },
  ],
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const camZoom = interpolate(frame, [0, durationInFrames], [1.0, 1.12], { extrapolateRight: 'clamp' });
  const pathLength = 1400;
  const dashOffset = interpolate(frame, [8, Math.max(20, durationInFrames - 15)], [pathLength, 0], {
    easing: Easing.inOut(Easing.cubic),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const polyPoints = searchZonePolygon.map((p) => `${p.x},${p.y}`).join(' ');
  const routeD =
    waypoints.length >= 2
      ? waypoints.map((wp, idx) => `${idx === 0 ? 'M' : 'L'} ${wp.x} ${wp.y}`).join(' ')
      : 'M 520 780 L 760 510 L 980 240';
  const targetWp = waypoints[Math.min(1, waypoints.length - 1)] || { x: 760, y: 510 };

  return (
    <AbsoluteFill style={{ backgroundColor: '#05070A', overflow: 'hidden', fontFamily: "'Noto Sans Arabic', sans-serif" }}>
      <div style={{ width: '100%', height: '100%', transform: `scale(${camZoom})`, transformOrigin: `${targetWp.x}px ${targetWp.y}px` }}>
        <svg width="1920" height="1080" viewBox="0 0 1920 1080">
          <polygon points={polyPoints} fill="rgba(229, 37, 33, 0.12)" stroke="#E52521" strokeWidth="2" strokeDasharray="10 6" />
          <path d={routeD} fill="none" stroke="#E52521" strokeWidth="3.5" strokeLinecap="round" strokeDasharray={pathLength} strokeDashoffset={dashOffset} />
          {waypoints.map((wp, idx) => {
            const wpSpring = spring({ frame: Math.max(0, frame - (idx * 14 + 5)), fps, config: { damping: 14 } });
            return (
              <g key={idx} transform={`translate(${wp.x}, ${wp.y}) scale(${wpSpring})`}>
                <circle r="7" fill="#E52521" stroke="#FFFFFF" strokeWidth="2" />
                <text x="16" y="-12" fill="#FFFFFF" fontSize="16" fontWeight="bold" fontFamily="monospace">{wp.label}</text>
              </g>
            );
          })}
        </svg>
      </div>
      <div style={{ position: 'absolute', top: 42, right: 60, left: 60, display: 'flex', justifyContent: 'space-between', direction: 'rtl' }}>
        <div style={{ background: 'rgba(8, 11, 16, 0.88)', borderRight: '4px solid #E52521', padding: '14px 24px' }}>
          <div style={{ color: '#FFFFFF', fontSize: 28, fontWeight: 800 }}>{arabicTitle}</div>
          <div style={{ color: '#8A99AD', fontSize: 14, fontFamily: 'monospace', direction: 'ltr' }}>{title} // {sectorCode} // {coordinates}</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
