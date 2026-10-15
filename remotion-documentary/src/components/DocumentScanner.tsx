import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing } from 'remotion';

export interface DocumentScannerProps {
  documentTitle?: string;
  archiveSource?: string;
  exhibitCode?: string;
  highlightedQuote?: string;
  arabicTranslation?: string;
  durationInFrames?: number;
}

export const DocumentScanner: React.FC<DocumentScannerProps> = ({
  documentTitle = 'FEDERAL BUREAU OF INVESTIGATION // TELETYPE ARCHIVE',
  archiveSource = 'NATIONAL ARCHIVES // RECORD GROUP 65',
  exhibitCode = 'EXHIBIT #14-B // DECLASSIFIED',
  highlightedQuote = 'AT APPROXIMATELY 20:13 PST, CABIN PRESSURE FLUCTUATION RECORDED',
  arabicTranslation = 'تم تسجيل تغير مفاجئ في ضغط المقصورة عند الساعة 20:13 مساءً فوق غابات واشنطن',
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const highlightProgress = interpolate(frame, [10, Math.max(25, durationInFrames - 15)], [0, 100], {
    easing: Easing.inOut(Easing.cubic),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{ backgroundColor: '#050608', display: 'flex', justifyContent: 'center', alignItems: 'center', fontFamily: "'Noto Sans Arabic', monospace, sans-serif" }}>
      <div style={{ width: 1260, background: '#11151C', border: '2px solid #2A3444', padding: '54px 68px', position: 'relative' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '2px solid #2A3444', paddingBottom: 20, fontFamily: 'monospace' }}>
          <div style={{ color: '#FFF', fontSize: 22, fontWeight: 800 }}>{documentTitle} // {archiveSource}</div>
          <div style={{ color: '#E52521', fontSize: 18, fontWeight: 800 }}>{exhibitCode}</div>
        </div>
        <div style={{ marginTop: 36, padding: '20px 26px', background: '#0A0D12', position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', top: 10, bottom: 10, left: 14, width: `${highlightProgress}%`, background: 'rgba(229, 37, 33, 0.42)' }} />
          <div style={{ position: 'relative', fontFamily: 'monospace', fontSize: 24, fontWeight: 900, color: '#FFF' }}>{highlightedQuote}</div>
        </div>
        <div style={{ marginTop: 32, borderRight: '5px solid #E52521', paddingRight: 22, direction: 'rtl', color: '#F8FAFC', fontSize: 28, fontWeight: 800 }}>
          {arabicTranslation}
        </div>
      </div>
    </AbsoluteFill>
  );
};
