import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring } from 'remotion';

export interface ChapterCardProps {
  chapterNumber?: number;
  arabicTitle?: string;
  englishSubtitle?: string;
  eraLabel?: string;
  durationInFrames?: number;
}

export const ChapterCard: React.FC<ChapterCardProps> = ({
  chapterNumber = 1,
  arabicTitle = 'الفصل الأول: لغز الرحلة ٣٠٥',
  englishSubtitle = 'CHAPTER I // THE HIJACKING OF FLIGHT 305',
  eraLabel = 'NOVEMBER 24, 1971 // PORTLAND TO SEATTLE',
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enterSpring = spring({ frame, fps, config: { damping: 16 } });

  return (
    <AbsoluteFill style={{ backgroundColor: '#040507', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', fontFamily: "'Noto Sans Arabic', sans-serif", direction: 'rtl' }}>
      <div style={{ fontFamily: 'monospace', fontSize: 20, letterSpacing: 8, color: '#E52521', fontWeight: 800, marginBottom: 18, direction: 'ltr' }}>{englishSubtitle}</div>
      <div style={{ fontSize: 64, fontWeight: 900, color: '#FFFFFF', transform: `scale(${0.92 + 0.08 * enterSpring})` }}>{arabicTitle}</div>
      <div style={{ fontFamily: 'monospace', fontSize: 17, letterSpacing: 4, color: '#94A3B8', marginTop: 24, direction: 'ltr' }}>{eraLabel} // CH-{String(chapterNumber).padStart(2, '0')}</div>
    </AbsoluteFill>
  );
};
