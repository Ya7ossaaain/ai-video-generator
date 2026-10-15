import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring } from 'remotion';

export interface TimelineComparisonProps {
  mode?: 'flowchart' | 'comparison';
  arabicHeader?: string;
  englishSubheader?: string;
  durationInFrames?: number;
}

export const TimelineComparison: React.FC<TimelineComparisonProps> = ({
  arabicHeader = 'المخطط الزمني المتفرع لنظريات التحقيق والمقارنة الجنائية',
  englishSubheader = 'CHRONOLOGICAL BRANCHING ANALYSIS & BEFORE/AFTER WIPE',
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 14 } });

  return (
    <AbsoluteFill style={{ backgroundColor: '#05070B', color: '#F8FAFC', fontFamily: "'Noto Sans Arabic', sans-serif", padding: '54px 72px', direction: 'rtl' }}>
      <div style={{ borderRight: '5px solid #E52521', paddingRight: 22, opacity: s }}>
        <div style={{ fontSize: 34, fontWeight: 900 }}>{arabicHeader}</div>
        <div style={{ fontFamily: 'monospace', fontSize: 15, color: '#94A3B8', direction: 'ltr', marginTop: 4 }}>{englishSubheader}</div>
      </div>
    </AbsoluteFill>
  );
};
