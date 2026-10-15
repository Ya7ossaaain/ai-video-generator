import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring } from 'remotion';

export interface EvidencePoint {
  text: string;
  type: 'pro' | 'con';
}

export interface ForensicDossierProps {
  mode?: 'suspect' | 'grid';
  subjectName?: string;
  arabicRole?: string;
  caseId?: string;
  statusLabel?: string;
  evidencePoints?: EvidencePoint[];
  durationInFrames?: number;
}

export const ForensicDossier: React.FC<ForensicDossierProps> = ({
  subjectName = 'DAN COOPER // UNSUB #305',
  arabicRole = 'الملف الجنائي للمشتبه به الرئيسي ومطابقة الأدلة',
  caseId = 'FBI-FILE // NORJAK-1971',
  statusLabel = 'UNIDENTIFIED // قيد التحقيق الجنائي',
  evidencePoints = [
    { text: 'تطابق الوصف الجسدي مع شهادات طاقم الرحلة 305', type: 'pro' },
    { text: 'خبرة تقنية بطائرات Boeing 727 والدرج الخلفي', type: 'pro' },
    { text: 'عدم تطابق البصمات الجزئية مع السجلات الفيدرالية', type: 'con' },
  ],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ backgroundColor: '#06080C', color: '#F1F5F9', fontFamily: "'Noto Sans Arabic', sans-serif", direction: 'rtl', padding: '54px 72px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '2px solid #1E293B', paddingBottom: 18 }}>
        <div>
          <div style={{ color: '#E52521', fontFamily: 'monospace', fontSize: 16, direction: 'ltr' }}>{caseId} // {subjectName}</div>
          <div style={{ fontSize: 34, fontWeight: 900, marginTop: 4 }}>{arabicRole}</div>
        </div>
        <div style={{ border: '2px solid #E52521', color: '#E52521', padding: '8px 20px', fontSize: 18, fontWeight: 800 }}>{statusLabel}</div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 22, marginTop: 42 }}>
        {evidencePoints.map((pt, idx) => {
          const appear = spring({ frame: Math.max(0, frame - idx * 10), fps, config: { damping: 14 } });
          const accent = pt.type === 'pro' ? '#2ECC71' : '#E52521';
          return (
            <div key={idx} style={{ opacity: appear, background: '#0B0F17', borderRight: `5px solid ${accent}`, padding: '22px 28px', fontSize: 24, fontWeight: 700 }}>
              {pt.type === 'pro' ? '✓ ' : '✗ '} {pt.text}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
