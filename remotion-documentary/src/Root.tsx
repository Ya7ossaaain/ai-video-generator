import React from 'react';
import {Composition} from 'remotion';
import {ChapterTransition} from './ChapterTransition';
import {MapOverlay} from './MapOverlay';
import {TimelineCard} from './TimelineCard';
import {Sequence, useCurrentFrame, AbsoluteFill} from 'remotion';

interface SceneData {
  type: 'chapter_transition' | 'map_overlay' | 'timeline_card';
  chapterNum: number;
  title: string;
  arabicText: string;
  durationInFrames: number;
}

interface DocProps {
  scenes: SceneData[];
  brandColors: {
    primary: string;
    secondary: string;
    dark: string;
    accent: string;
  };
}

const defaultColors = {
  primary: '#C47A1A',
  secondary: '#FFFFFF',
  dark: '#0A0C10',
  accent: '#D4891A',
};

const DocumentaryMain: React.FC<DocProps> = ({scenes, brandColors}) => {
  const colors = {...defaultColors, ...brandColors};
  let currentFrame = 0;

  return (
    <AbsoluteFill style={{backgroundColor: colors.dark}}>
      {scenes.map((scene, i) => {
        const from = currentFrame;
        currentFrame += scene.durationInFrames;
        return (
          <Sequence key={i} from={from} durationInFrames={scene.durationInFrames}>
            {scene.type === 'chapter_transition' && (
              <ChapterTransition
                chapterNum={scene.chapterNum}
                title={scene.title}
                colors={colors}
              />
            )}
            {scene.type === 'map_overlay' && (
              <MapOverlay
                arabicText={scene.arabicText}
                colors={colors}
              />
            )}
            {scene.type === 'timeline_card' && (
              <TimelineCard
                arabicText={scene.arabicText}
                title={scene.title}
                colors={colors}
              />
            )}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export const Root: React.FC = () => {
  return (
    <>
      <Composition
        id="DocumentaryComposition"
        component={DocumentaryMain}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          scenes: [],
          brandColors: defaultColors,
        }}
        calculateMetadata={({props}) => {
          const totalFrames = (props.scenes || []).reduce(
            (acc: number, s: SceneData) => acc + s.durationInFrames,
            0
          );
          return {
            durationInFrames: Math.max(totalFrames, 1),
          };
        }}
      />
    </>
  );
};
