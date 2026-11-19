import React, {useEffect, useState} from 'react';
import {
  AbsoluteFill, Audio, OffthreadVideo, Sequence, continueRender, delayRender,
  interpolate, spring, staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';

type Kelime = {w: string; s: number; e: number};
export type ShortProps = {
  sure: number;
  kaynak: 'ham' | 'bilesik';
  baslik: string;
  baslikEmoji: string;
  yayinci: string;
  altyazi: {s: number; e: number; k: Kelime[]}[];
  emojiler: {t: number; e: string}[];
  zoomlar: number[];
  sfx: {f: string; t: number; v: number; sure?: number}[];
};

// --- yerlesim (1080x1920). YouTube Shorts / Reels guvenli alanlari:
// ust ~200 px, alt ~420 px ve sag ~140 px arayuz altinda kalir; yazilar oraya konmaz.
const OYUN_Y = 630;          // oyun karesinin ust kenari
const OYUN_G = 1400;         // oyun goruntusunun genisligi (1080'den tasar, kenarlar kirpilir)
const OYUN_Y_YUK = Math.round((OYUN_G * 9) / 16); // 788
// oyunun alt %11'i (oyunun kendi altyazilari, harita) gizlenir
const GORUNEN = Math.round(OYUN_Y_YUK * 0.89);
// altyazi oyun karesinin alt kismina biner: oyunun kendi altyazisini da kapatir
const ALTYAZI_Y = OYUN_Y + GORUNEN - 30;
const SARI = '#FFE14D';

const FontYukle: React.FC = () => {
  const [h] = useState(() => delayRender('fontlar'));
  useEffect(() => {
    const yukle = async () => {
      const fontlar = [
        new FontFace('Anton', `url(${staticFile('fonts/Anton-Regular.ttf')})`),
        new FontFace('Montserrat', `url(${staticFile('fonts/Montserrat.ttf')})`, {weight: '100 900'}),
      ];
      for (const f of fontlar) {
        await f.load();
        (document.fonts as any).add(f);
      }
      continueRender(h);
    };
    yukle().catch(() => continueRender(h));
  }, [h]);
  return null;
};

const Video: React.FC<{kaynak: ShortProps['kaynak']; style: React.CSSProperties}> = ({kaynak, style}) => (
  <OffthreadVideo src={staticFile('girdi/video.mp4')} muted style={style} />
);

const Arkaplan: React.FC<{kaynak: ShortProps['kaynak']}> = ({kaynak}) => {
  // oyun goruntusu tum ekrani kaplayacak kadar buyutulur ve bulaniklastirilir
  const k = 1920 / 608;
  const stil: React.CSSProperties =
    kaynak === 'ham'
      ? {position: 'absolute', height: 1920, width: (1920 * 16) / 9, left: (1080 - (1920 * 16) / 9) / 2, top: 0}
      : {position: 'absolute', width: 1080 * k, height: 1920 * k, left: (1080 - 1080 * k) / 2, top: -656 * k};
  return (
    <AbsoluteFill style={{overflow: 'hidden', backgroundColor: '#0b0b10'}}>
      <Video kaynak={kaynak} style={{...stil, filter: 'blur(36px) brightness(0.55) saturate(1.4)'}} />
      <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(0,0,0,0.45) 0%, rgba(0,0,0,0) 35%, rgba(0,0,0,0) 65%, rgba(0,0,0,0.55) 100%)'}} />
    </AbsoluteFill>
  );
};

const OyunKaresi: React.FC<{p: ShortProps}> = ({p}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  // giris: hafif buyuyerek gelir
  let olcek = interpolate(frame, [0, 8], [1.12, 1], {extrapolateRight: 'clamp'});
  let titre = 0;
  for (const z of p.zoomlar) {
    const d = t - z;
    if (d >= 0 && d < 1.4) {
      olcek *= interpolate(d, [0, 0.12, 0.95, 1.4], [1, 1.2, 1.17, 1], {extrapolateRight: 'clamp'});
      if (d < 0.35) titre = Math.sin(frame * 2.3) * 9 * (1 - d / 0.35);
    }
  }
  const s = OYUN_G / 1080;
  const videoStil: React.CSSProperties =
    p.kaynak === 'ham'
      ? {position: 'absolute', left: (1080 - OYUN_G) / 2, top: 0, width: OYUN_G, height: OYUN_Y_YUK}
      : {position: 'absolute', left: (1080 - OYUN_G) / 2, top: -656 * s, width: OYUN_G, height: 1920 * s};
  return (
    <div style={{position: 'absolute', top: OYUN_Y, left: 0, width: 1080, height: GORUNEN, overflow: 'hidden',
      boxShadow: '0 0 60px rgba(0,0,0,0.6)'}}>
      <div style={{position: 'absolute', inset: 0, transform: `translate(${titre}px, ${titre * 0.6}px) scale(${olcek})`}}>
        <Video kaynak={p.kaynak} style={{...videoStil, filter: 'brightness(1.12) contrast(1.08) saturate(1.2)'}} />
      </div>
    </div>
  );
};

const Ilerleme: React.FC<{sure: number}> = ({sure}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const oran = Math.min(1, frame / fps / sure);
  return (
    <div style={{position: 'absolute', top: OYUN_Y + GORUNEN, left: 0, width: 1080, height: 12, background: 'rgba(255,255,255,0.18)'}}>
      <div style={{width: `${oran * 100}%`, height: '100%', background: SARI, boxShadow: `0 0 18px ${SARI}`}} />
    </div>
  );
};

const Baslik: React.FC<{p: ShortProps}> = ({p}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = spring({frame, fps, config: {damping: 11, stiffness: 160}});
  const salla = Math.sin(frame / 9) * 1.2;
  return (
    <div style={{position: 'absolute', top: 270, left: 70, width: 870, display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
      <div style={{
        transform: `scale(${g}) rotate(${salla - 1.5}deg)`, background: 'white', color: '#111',
        padding: '18px 30px 20px', borderRadius: 26, fontFamily: 'Montserrat', fontWeight: 900,
        fontSize: 64, lineHeight: 1.08, textAlign: 'center', textTransform: 'uppercase',
        boxShadow: '0 12px 0 #000, 0 18px 40px rgba(0,0,0,0.5)', letterSpacing: -1,
      }}>
        {p.baslik} <span style={{fontFamily: 'Noto Color Emoji'}}>{p.baslikEmoji}</span>
      </div>
    </div>
  );
};

const Altyazi: React.FC<{p: ShortProps}> = ({p}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const g = p.altyazi.find((x) => t >= x.s && t < x.e);
  if (!g) return null;
  const girisKare = Math.round(g.s * fps);
  const pop = spring({frame: frame - girisKare, fps, config: {damping: 9, stiffness: 220}});
  return (
    <div style={{position: 'absolute', top: ALTYAZI_Y - 90, left: 60, width: 880, height: 180,
      display: 'flex', alignItems: 'center', justifyContent: 'center', flexWrap: 'wrap', gap: '0 22px',
      transform: `scale(${0.7 + 0.3 * pop})`}}>
      {g.k.map((k, i) => {
        const aktif = t >= k.s;
        const simdi = t >= k.s && t < k.e + 0.05;
        return (
          <span key={i} style={{
            fontFamily: 'Anton', fontSize: simdi ? 104 : 96, textTransform: 'uppercase', lineHeight: 1.05,
            color: simdi ? SARI : aktif ? 'white' : 'rgba(255,255,255,0.85)',
            WebkitTextStroke: '12px black', paintOrder: 'stroke fill',
            textShadow: '0 8px 0 rgba(0,0,0,0.9)',
            transform: simdi ? 'rotate(-2deg) translateY(-6px)' : 'none',
          }}>{k.w.replace(/[.,!?]+$/, '')}</span>
        );
      })}
    </div>
  );
};

const YER = [[160, 700], [780, 760], [200, 1040], [770, 1000], [480, 680]];

const Emojiler: React.FC<{p: ShortProps}> = ({p}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  return (
    <>
      {p.emojiler.map((e, i) => {
        const d = t - e.t;
        if (d < 0 || d > 1.5) return null;
        const g = spring({frame: frame - Math.round(e.t * fps), fps, config: {damping: 8, stiffness: 200}});
        const cik = interpolate(d, [1.2, 1.5], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
        const [x, y] = YER[i % YER.length];
        return (
          <div key={i} style={{
            position: 'absolute', left: x - 90, top: y - 90 - d * 40, fontSize: 170,
            fontFamily: 'Noto Color Emoji', transform: `scale(${g * cik}) rotate(${Math.sin(d * 9) * 12}deg)`,
            filter: 'drop-shadow(0 10px 18px rgba(0,0,0,0.55))',
          }}>{e.e}</div>
        );
      })}
    </>
  );
};

const Kapanis: React.FC<{sure: number}> = ({sure}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const bas = Math.round((sure - 3) * fps);
  if (frame < bas) return null;
  const g = spring({frame: frame - bas, fps, config: {damping: 10, stiffness: 180}});
  return (
    <div style={{position: 'absolute', top: OYUN_Y + 40, left: 0, width: 960, display: 'flex', justifyContent: 'center'}}>
      <div style={{transform: `scale(${g}) rotate(-3deg)`, background: SARI, color: '#111', fontFamily: 'Montserrat',
        fontWeight: 900, fontSize: 52, padding: '14px 30px', borderRadius: 22, boxShadow: '0 8px 0 #000'}}>
        WAIT FOR PART 2 <span style={{fontFamily: 'Noto Color Emoji'}}>👀</span>
      </div>
    </div>
  );
};

const Flas: React.FC<{zoomlar: number[]}> = ({zoomlar}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  let o = interpolate(frame, [0, 6], [0.7, 0], {extrapolateRight: 'clamp'});
  for (const z of zoomlar) {
    const d = t - z;
    if (d >= 0 && d < 0.2) o = Math.max(o, interpolate(d, [0, 0.2], [0.45, 0]));
  }
  return <AbsoluteFill style={{background: 'white', opacity: o, pointerEvents: 'none'}} />;
};

export const Short: React.FC<ShortProps> = (p) => {
  const {fps} = useVideoConfig();
  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      <FontYukle />
      <Arkaplan kaynak={p.kaynak} />
      <OyunKaresi p={p} />
      <Ilerleme sure={p.sure} />
      <Emojiler p={p} />
      <Baslik p={p} />
      <Altyazi p={p} />
      <Kapanis sure={p.sure} />
      <Flas zoomlar={p.zoomlar} />
      <Audio src={staticFile('girdi/ses.wav')} />
      {p.sfx.map((s, i) => (
        <Sequence key={i} from={Math.round(s.t * fps)} durationInFrames={s.sure ? Math.max(1, Math.round(s.sure * fps)) : undefined}>
          <Audio src={staticFile(`sfx/${s.f}`)} volume={s.v} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
