import { ImageResponse } from 'next/og';

export const alt = 'AI Evaluator — healthcare simulation, thoughtfully connected';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

/** A local brand preview; it introduces no third-party image or tracking requests. */
export default function OpenGraphImage() {
  return new ImageResponse(
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', padding: '64px 80px', background: 'linear-gradient(120deg, #fcfcfe, #eee9fc)', color: '#17213b', fontFamily: 'sans-serif' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 18, marginBottom: 70 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 60, height: 60, borderRadius: 14, background: '#5b3fd6' }}>
          <svg width="38" height="38" viewBox="0 0 24 24" fill="none"><path d="M3.4 14 8 18.6 13.8 9.8" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /><path d="M17.8 2.6 19.05 4.75 21.2 6 19.05 7.25 17.8 9.4 16.55 7.25 14.4 6 16.55 4.75Z" fill="white" /></svg>
        </div>
        <span style={{ fontSize: 34, fontWeight: 600 }}>AI Evaluator</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', fontSize: 76, fontWeight: 600, lineHeight: 1.1, letterSpacing: '-3px' }}>
        <span>Bring clinical learning</span><span style={{ color: '#5b3fd6' }}>to life.</span>
      </div>
      <div style={{ display: 'flex', fontSize: 26, color: '#4b556b', marginTop: 40 }}>Healthcare simulation, thoughtfully connected.</div>
    </div>,
    size,
  );
}
