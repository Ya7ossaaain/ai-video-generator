import React from 'react';
import {useCurrentFrame, useVideoConfig, interpolate, Easing} from 'remotion';
import {loadFont} from '@remotion/google-fonts/NotoSansArabic';

const {fontFamily} = loadFont();

interface Props {
  chapterNum: number;
  title: string;
  colors: {
    primary: string;
    secondary: string;
    dark: string;
    accent: string;
  };
}

export const ChapterTransition: React.FC<Props> = ({chapterNum, title, colors}) => {
  const frame = useCurrentFrame();
  const {durationInFrames, fps} = useVideoConfig();

  const fadeIn = interpolate(frame, [0, fps * 0.3], [0, 1], {
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

  const fadeOut = interpolate(
    frame,
    [durationInFrames - fps * 0.3, durationInFrames],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
  );

  const opacity = Math.min(fadeIn, fadeOut);

  const slideUp = interpolate(frame, [0, fps * 0.4], [30, 0], {
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        background: `radial-gradient(ellipse at center, ${colors.dark} 0%, #000000 100%)`,
        fontFamily,
        direction: 'rtl',
      }}
    >
      <div
        style={{
          opacity,
          transform: `translateY(${slideUp}px)`,
          textAlign: 'center',
        }}
      >
        <div
          style={{
            fontSize: 36,
            color: colors.primary,
            marginBottom: 20,
            letterSpacing: 4,
            fontWeight: 400,
          }}
        >
          محور التحقيق {String(chapterNum).padStart(2, '0')}
        </div>
        <div
          style={{
            fontSize: 64,
            color: colors.secondary,
            fontWeight: 700,
            textShadow: `0 4px 12px rgba(0,0,0,0.8), 0 0 40px ${colors.primary}33`,
            maxWidth: 1400,
            lineHeight: 1.4,
          }}
        >
          {title}
        </div>
      </div>
      {/* Cinematic vignette */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background:
            'radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.6) 100%)',
          pointerEvents: 'none',
        }}
      />
    </div>
  );
};
