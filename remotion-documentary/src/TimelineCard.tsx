import React from 'react';
import {useCurrentFrame, useVideoConfig, interpolate, Easing} from 'remotion';
import {loadFont} from '@remotion/google-fonts/NotoSansArabic';

const {fontFamily} = loadFont();

interface Props {
  title: string;
  arabicText: string;
  colors: {
    primary: string;
    secondary: string;
    dark: string;
    accent: string;
  };
}

export const TimelineCard: React.FC<Props> = ({title, arabicText, colors}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  const fadeIn = interpolate(frame, [0, fps * 0.4], [0, 1], {
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - fps * 0.4, durationInFrames],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
  );
  const opacity = Math.min(fadeIn, fadeOut);

  const lineWidth = interpolate(frame, [fps * 0.2, fps * 0.8], [0, 100], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.inOut(Easing.cubic),
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
        background: `radial-gradient(ellipse at center, #0f0f1a 0%, ${colors.dark} 100%)`,
        fontFamily,
        direction: 'rtl',
      }}
    >
      <div style={{opacity, textAlign: 'center'}}>
        <div
          style={{
            fontSize: 38,
            color: colors.primary,
            fontWeight: 500,
            marginBottom: 24,
          }}
        >
          {title}
        </div>
        <div
          style={{
            width: `${lineWidth}%`,
            height: 3,
            backgroundColor: colors.primary,
            margin: '0 auto 30px',
            borderRadius: 2,
          }}
        />
        <div
          style={{
            fontSize: 52,
            color: colors.secondary,
            fontWeight: 700,
            lineHeight: 1.5,
            maxWidth: 1400,
            textShadow: `0 3px 10px rgba(0,0,0,0.7)`,
          }}
        >
          {arabicText}
        </div>
      </div>
      <div
        style={{
          position: 'absolute',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.5) 100%)',
          pointerEvents: 'none',
        }}
      />
    </div>
  );
};
