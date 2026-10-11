import React from 'react';
import { Sequence, useCurrentFrame, interpolate, spring, Easing } from 'remotion';

// --- 1. خامة الحبيبات السينمائية والظلال (Atmospheric Grain & Vignette) ---
const FilmGrainOverlay: React.FC = () => (
  <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 100 }}>
    <div style={{
      width: '100%',
      height: '100%',
      background: 'radial-gradient(circle at center, transparent 35%, rgba(0, 0, 0, 0.92) 100%)',
    }} />
    <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.08 }}>
      <filter id="noiseFilter">
        <feTurbulence type="fractalNoise" baseFrequency="0.75" numOctaves="3" stitchTiles="stitch" />
      </filter>
      <rect width="100%" height="100%" filter="url(#noiseFilter)" />
    </svg>
  </div>
);

// --- 2. بيانات الملاحة الحية على الشاشة (HUD Telemetry) ---
const TelemetryHUD: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [10, 30], [0, 0.75], { extrapolateRight: 'clamp' });
  return (
    <div style={{
      position: 'absolute',
      bottom: 45,
      left: 60,
      fontFamily: 'monospace',
      fontSize: 16,
      letterSpacing: 4,
      color: '#A0A0A0',
      opacity,
      zIndex: 50,
      borderLeft: '2px solid #E52521',
      paddingLeft: 14
    }}>
      {text}
    </div>
  );
};

// --- المشهد 1: اقتراب طائرة الـ 727 وفتح الدرج الخلفي (0s - 12s) ---
const Scene1Airplane: React.FC = () => {
  const frame = useCurrentFrame();

  const scale = interpolate(frame, [0, 240, 360], [0.2, 1.35, 1.9], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateRight: 'clamp',
  });

  const rotateX = interpolate(frame, [80, 260], [0, 24], { extrapolateRight: 'clamp' });
  const rotateY = interpolate(frame, [60, 280], [0, 48], { extrapolateRight: 'clamp' });
  const stairDeploy = interpolate(frame, [200, 300], [0, 38], {
    easing: Easing.out(Easing.quad),
    extrapolateRight: 'clamp',
  });

  return (
    <div style={{ width: '100%', height: '100%', background: '#050505', display: 'flex', justifyContent: 'center', alignItems: 'center', perspective: 1200 }}>
      <TelemetryHUD text="FLIGHT 305 // BOEING 727-051 // CRUISE ALT: 10,000 FT // 170 KTS" />

      {/* خطوط سرعة الرياح الشعاعية */}
      <svg style={{ position: 'absolute', width: '100%', height: '100%', opacity: 0.18 }}>
        {[...Array(20)].map((_, i) => (
          <line
            key={i}
            x1="50%"
            y1="50%"
            x2={`${50 + 65 * Math.cos((i * Math.PI) / 10)}%`}
            y2={`${50 + 65 * Math.sin((i * Math.PI) / 10)}%`}
            stroke="#ffffff"
            strokeWidth="1.2"
            strokeDasharray="12,25"
          />
        ))}
      </svg>

      {/* مجسم طائرة الـ 727 الخطي النقي */}
      <div style={{ transform: `scale(${scale}) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`, transformStyle: 'preserve-3d' }}>
        <svg width="680" height="340" viewBox="0 0 680 340" fill="none">
          {/* جسم الطائرة */}
          <path d="M 60 170 Q 240 145, 540 155 Q 620 158, 650 170 Q 580 182, 380 188 L 140 188 Z" stroke="#FFFFFF" strokeWidth="2.4" fill="#080808" />
          {/* الجناح الرئيسي والجنيحات المفتوحة */}
          <path d="M 310 175 L 240 260 L 290 260 L 380 180" stroke="#FFFFFF" strokeWidth="2" fill="#0C0C0C" />
          <polygon points="245,255 285,255 305,240 265,240" fill="#E52521" opacity="0.8" />
          {/* الذيل والمحركات الخلفية الثلاثية المميزة للـ 727 */}
          <path d="M 530 155 L 600 65 L 650 65 L 620 155" stroke="#FFFFFF" strokeWidth="2.4" fill="#080808" />
          <ellipse cx="550" cy="140" rx="28" ry="11" stroke="#FFFFFF" strokeWidth="1.6" fill="#050505" />
          <ellipse cx="550" cy="185" rx="28" ry="11" stroke="#FFFFFF" strokeWidth="1.6" fill="#050505" />
          {/* الدرج الخلفي المفتوح بلون أحمر متوهج */}
          <g transform={`translate(550, 175) rotate(${stairDeploy})`}>
            <polygon points="0,0 52,28 40,34 -6,6" fill="#E52521" stroke="#FFFFFF" strokeWidth="1.2" />
          </g>
        </svg>
      </div>
    </div>
  );
};

// --- المشهد 2: القفزة والسقوط الحر وسط الرياح (12s - 25s) ---
const Scene2Freefall: React.FC = () => {
  const frame = useCurrentFrame();

  const rotation = interpolate(frame, [0, 390], [0, 720]);
  const posY = interpolate(frame, [0, 390], [-60, 90]);
  const posX = interpolate(frame, [0, 200, 390], [-40, 50, -20]);
  const cameraDrift = interpolate(frame, [0, 390], [1, 1.15]);

  return (
    <div style={{ width: '100%', height: '100%', background: '#040404', display: 'flex', justifyContent: 'center', alignItems: 'center', position: 'relative', transform: `scale(${cameraDrift})` }}>
      <TelemetryHUD text="ZONE: LAKE MERWIN // ELEVATION: 8,200 FT // FREEZING NIGHT TEMPEST" />

      {/* ذرات المطر والرياح الصاعدة العنيفة */}
      <div style={{ position: 'absolute', inset: 0, opacity: 0.35 }}>
        {[...Array(40)].map((_, i) => (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: `${(i * 2.5) * 10}%`,
              top: `${((frame * 25 + i * 90) % 1200) - 100}px`,
              width: '1px',
              height: `${25 + (i % 5) * 15}px`,
              background: 'linear-gradient(to top, rgba(255,255,255,0.8), transparent)'
            }}
          />
        ))}
      </div>

      {/* مجسم كوبر الساقط وهو يتقلب في الفراغ */}
      <div style={{ transform: `translate(${posX}px, ${posY}px) rotate(${rotation}deg)` }}>
        <svg width="200" height="200" viewBox="0 0 100 100">
          <path
            d="M 50 18 C 54 18 57 15 57 12 C 57 9 54 6 50 6 C 46 6 43 9 43 12 C 43 15 46 18 50 18 Z 
               M 40 22 L 60 22 L 72 36 L 65 40 L 58 30 L 58 52 L 70 78 L 61 82 L 50 58 L 39 82 L 30 78 L 42 52 L 42 30 L 35 40 L 28 36 Z"
            fill="#E52521"
          />
          <rect x="42" y="24" width="16" height="24" rx="4" fill="#800D0B" />
        </svg>
      </div>

      {/* نص إذاعي أرشيفي بالأسفل */}
      <div style={{
        position: 'absolute',
        bottom: 110,
        color: '#D0D0D0',
        fontFamily: 'monospace',
        fontSize: 22,
        letterSpacing: 3,
        textAlign: 'center',
        width: '80%',
        opacity: interpolate(frame, [30, 60, 330, 370], [0, 1, 1, 0])
      }}>
        "A DARING PARACHUTE ESCAPE FROM A FLYING 727..."
      </div>
    </div>
  );
};

// --- المشهد 3: غابة الصنوبر الباردة وتطاير الطيور (25s - 37s) ---
const Scene3Forest: React.FC = () => {
  const frame = useCurrentFrame();

  const cameraZoom = interpolate(frame, [0, 360], [1, 1.28]);
  const fallerY = interpolate(frame, [0, 360], [120, 520]);
  const fallerScale = interpolate(frame, [0, 360], [0.9, 0.08]);

  // مسار الطيور المتطايرة فجأة من بين الأشجار
  const birdsFlyX = interpolate(frame, [110, 360], [0, -520]);
  const birdsFlyY = interpolate(frame, [110, 360], [0, -380]);
  const birdsOpacity = interpolate(frame, [110, 130, 330, 360], [0, 1, 1, 0]);

  return (
    <div style={{ width: '100%', height: '100%', background: '#050505', position: 'relative', overflow: 'hidden', transform: `scale(${cameraZoom})` }}>
      <TelemetryHUD text="DROP ZONE: SOUTHWEST WASHINGTON // UNCHARTED WILDERNESS" />

      {/* كوبر يبتعد متلاشياً في عمق الغابة */}
      <div style={{ position: 'absolute', left: '50%', top: fallerY, transform: `translate(-50%, 0) scale(${fallerScale})`, zIndex: 2 }}>
        <div style={{ width: 44, height: 44, backgroundColor: '#E52521', borderRadius: '50%', filter: 'drop-shadow(0 0 10px #E52521)' }} />
      </div>

      {/* أسراب الطيور السوداء المتطايرة */}
      <div style={{ position: 'absolute', left: '51%', top: '56%', transform: `translate(${birdsFlyX}px, ${birdsFlyY}px)`, opacity: birdsOpacity, zIndex: 10 }}>
        <svg width="160" height="100" viewBox="0 0 100 60">
          <path d="M 10 20 Q 20 10 30 20 Q 40 10 50 20" stroke="#000000" strokeWidth="3.2" fill="none" />
          <path d="M 52 35 Q 60 25 68 35 Q 76 25 84 35" stroke="#000000" strokeWidth="2.8" fill="none" />
        </svg>
      </div>

      {/* قمم أشجار الصنوبر (Pacific Northwest Forest) */}
      <div style={{ position: 'absolute', bottom: 0, width: '100%', height: '60%', zIndex: 5 }}>
        <svg width="100%" height="100%" viewBox="0 0 1920 600" preserveAspectRatio="none">
          <defs>
            <linearGradient id="mistFog" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#0B0B0B" stopOpacity="1" />
            </linearGradient>
          </defs>
          {[...Array(52)].map((_, i) => {
            const x = i * 38;
            const h = 240 + (i % 8) * 38;
            return (
              <polygon
                key={i}
                points={`${x},600 ${x + 24},${600 - h} ${x + 48},600`}
                fill={i % 2 === 0 ? "url(#mistFog)" : "#222222"}
                opacity={0.65 + (i % 3) * 0.15}
              />
            );
          })}
        </svg>
      </div>
    </div>
  );
};

// --- المشهد 4: العنوان الفخم وتظليل تذكرة الطيران بالماركر (37s - 50s) ---
const Scene4TitleAndDocument: React.FC = () => {
  const frame = useCurrentFrame();

  const titleScale = spring({ frame, fps: 30, config: { damping: 14 } });
  const docTransition = interpolate(frame, [150, 190], [0, 1], { extrapolateRight: 'clamp' });
  const highlightWidth = interpolate(frame, [210, 270], [0, 320], { extrapolateRight: 'clamp' });
  const stampScale = spring({ frame: frame - 280, fps: 30, config: { damping: 9 } });

  return (
    <div style={{ width: '100%', height: '100%', background: '#000000', display: 'flex', justifyContent: 'center', alignItems: 'center', position: 'relative' }}>
      
      {/* 4.1: ضربة الفرشاة وظهور العنوان الأيقوني */}
      <div style={{
        position: 'absolute',
        opacity: 1 - docTransition,
        transform: `scale(${titleScale})`,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '40px 80px',
        background: '#0B0D11',
        border: '1px solid #1E232B',
        boxShadow: '0 0 100px rgba(0,0,0,0.95)'
      }}>
        <span style={{ color: '#E0E0E0', fontSize: 26, letterSpacing: 12, fontWeight: 900, fontFamily: 'sans-serif' }}>
          THE SEARCH FOR
        </span>
        <span style={{ color: '#E52521', fontSize: 90, fontFamily: 'cursive, "Brush Script MT", Georgia', fontStyle: 'italic', marginTop: 12, textShadow: '0 0 35px rgba(229,37,33,0.5)' }}>
          D. B. Cooper
        </span>
      </div>

      {/* 4.2: الانتقال لفحص وثيقة التذكرة وتظليل اسم دان كوبر بالماركر الأصفر */}
      <div style={{
        position: 'absolute',
        opacity: docTransition,
        transform: `scale(${interpolate(frame, [180, 380], [0.95, 1.05])})`,
        width: 820,
        height: 480,
        background: '#12151B',
        border: '2px solid #2B3340',
        boxShadow: '0 0 80px rgba(0,0,0,0.9)',
        padding: 40,
        fontFamily: 'monospace',
        color: '#C0C0C0'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '2px solid #333C4D', paddingBottom: 15 }}>
          <span style={{ color: '#FFFFFF', fontWeight: 'bold' }}>NORTHWEST ORIENT AIRLINES</span>
          <span style={{ color: '#E52521' }}>FLIGHT 305 // SEATTLE</span>
        </div>

        <div style={{ marginTop: 40, fontSize: 20 }}>
          <div>PASSENGER NAME:</div>
          <div style={{ position: 'relative', display: 'inline-block', marginTop: 10 }}>
            {/* خط التظليل الأصفر (Yellow Highlighter Effect) */}
            <div style={{
              position: 'absolute',
              top: -4,
              left: -8,
              height: 38,
              width: highlightWidth,
              backgroundColor: 'rgba(255, 235, 59, 0.65)',
              mixBlendMode: 'difference',
              borderRadius: 3
            }} />
            <span style={{ fontSize: 32, color: '#FFFFFF', letterSpacing: 6, fontWeight: 900 }}>
              DAN COOPER
            </span>
          </div>
        </div>

        <div style={{ marginTop: 35, fontSize: 16, lineHeight: 1.8, color: '#8892A0' }}>
          TICKET NO: 162-444-06773-0<br />
          FARE: $20.00 (PAID IN CASH)<br />
          DEPARTURE: PORTLAND INTL (PDX)
        </div>

        {/* ختم التحقيق الأحمر (EVIDENCE #1 STAMP) */}
        {frame > 280 && (
          <div style={{
            position: 'absolute',
            right: 50,
            bottom: 40,
            transform: `scale(${stampScale}) rotate(-12deg)`,
            border: '4px solid #E52521',
            color: '#E52521',
            padding: '10px 24px',
            fontSize: 28,
            fontWeight: 900,
            letterSpacing: 4,
            boxShadow: '0 0 20px rgba(229,37,33,0.3)'
          }}>
            EVIDENCE #1
          </div>
        )}
      </div>
    </div>
  );
};

// --- المجمع الرئيسي للمشهد الكامل (50 ثانية = 1500 إطار) ---
export const LemminoExperience: React.FC = () => {
  return (
    <div style={{ width: 1920, height: 1080, background: '#000000', position: 'relative', overflow: 'hidden' }}>
      <FilmGrainOverlay />

      <Sequence from={0} durationInFrames={360}>
        <Scene1Airplane />
      </Sequence>

      <Sequence from={360} durationInFrames={390}>
        <Scene2Freefall />
      </Sequence>

      <Sequence from={750} durationInFrames={360}>
        <Scene3Forest />
      </Sequence>

      <Sequence from={1110} durationInFrames={390}>
        <Scene4TitleAndDocument />
      </Sequence>
    </div>
  );
};
