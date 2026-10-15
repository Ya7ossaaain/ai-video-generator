import React from 'react';
import { Composition } from 'remotion';
import { VectorMapTracker, VectorMapTrackerProps } from './components/VectorMapTracker';
import { ForensicDossier, ForensicDossierProps } from './components/ForensicDossier';
import { HudOverlay, HudOverlayProps } from './components/HudOverlay';
import { DocumentScanner, DocumentScannerProps } from './components/DocumentScanner';
import { TimelineComparison, TimelineComparisonProps } from './components/TimelineComparison';
import { ChapterCard, ChapterCardProps } from './components/ChapterCard';

const dynamicDuration = <T extends { durationInFrames?: number }>({ props }: { props: T }) => {
  return {
    durationInFrames: Math.max(15, Number(props.durationInFrames || 90)),
    fps: 30,
    width: 1920,
    height: 1080,
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="VectorMapTracker"
        component={VectorMapTracker as React.FC<VectorMapTrackerProps>}
        durationInFrames={90}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ durationInFrames: 90 }}
        calculateMetadata={dynamicDuration}
      />
      <Composition
        id="ForensicDossier"
        component={ForensicDossier as React.FC<ForensicDossierProps>}
        durationInFrames={90}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ durationInFrames: 90 }}
        calculateMetadata={dynamicDuration}
      />
      <Composition
        id="HudOverlay"
        component={HudOverlay as React.FC<HudOverlayProps>}
        durationInFrames={90}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ durationInFrames: 90 }}
        calculateMetadata={dynamicDuration}
      />
      <Composition
        id="DocumentScanner"
        component={DocumentScanner as React.FC<DocumentScannerProps>}
        durationInFrames={90}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ durationInFrames: 90 }}
        calculateMetadata={dynamicDuration}
      />
      <Composition
        id="TimelineComparison"
        component={TimelineComparison as React.FC<TimelineComparisonProps>}
        durationInFrames={90}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ durationInFrames: 90 }}
        calculateMetadata={dynamicDuration}
      />
      <Composition
        id="ChapterCard"
        component={ChapterCard as React.FC<ChapterCardProps>}
        durationInFrames={90}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ durationInFrames: 90 }}
        calculateMetadata={dynamicDuration}
      />
    </>
  );
};
