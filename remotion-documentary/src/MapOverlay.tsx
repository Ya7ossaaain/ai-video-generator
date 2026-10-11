import React from 'react';
import {useCurrentFrame, useVideoConfig, interpolate, Easing} from 'remotion';
import {loadFont} from '@remotion/google-fonts/NotoSansArabic';

const {fontFamily} = loadFont();

interface Props {
  arabicText: string;
  colors: {
    primary: string;
    secondary: string;
    dark: string;
    accent: string;
  };
}

export const MapOverlay: React.FC<Props> = ({arabicText, colors}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  const fadeIn = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateRight: 'clamp',
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - fps * 0.5, durationInFrames],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
  );
  const opacity = Math.min(fadeIn, fadeOut);

  const scale = interpolate(frame, [0, fps * 0.6], [1.05, 1.0], {
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        background: `linear-gradient(135deg, ${colors.dark} 0%, #1a1a2e 50%, ${colors.dark} 100%)`,
        fontFamily,
        direction: 'rtl',
      }}
    >
      <div
        style={{
          opacity,
          transform: `scale(${scale})`,
          padding: '60px 80px',
          border: `2px solid ${colors.primary}66`,
          borderRadius: 16,
          backgroundColor: `${colors.dark}CC`,
          maxWidth: 1600,
          textAlign: 'center',
        }}
      >
        <div
          style={{
            fontSize: 48,
            color: colors.secondary,
            fontWeight: 600,
            lineHeight: 1.6,
            textShadow: `0 2px 8px rgba(0,0,0,0.6)`,
          }}
        >
          {arabicText}
        </div>
      </div>
    </div>
  );
};
