import { redirect } from 'next/navigation';
import { DownloadIcon, Card, CardBody } from '@pms/ui';
import { apiRequest, ApiError } from '@/lib/api';
import { downloadSession, type DesktopRelease } from '@/lib/downloads';

export const metadata = { title: 'Downloads' };

export default async function DownloadsPage() {
  let token: string;
  try { token = (await downloadSession()).token; }
  catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect('/login');
    if (error instanceof ApiError && error.status === 403) redirect('/home');
    throw error;
  }
  let releases: DesktopRelease[] = [];
  let unavailable = false;
  try { releases = (await apiRequest<{ items: DesktopRelease[] }>('/downloads', { token })).items; }
  catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect('/login');
    if (error instanceof ApiError && error.status === 403) redirect('/home');
    unavailable = true;
  }
  return <div className="desktop-downloads">
    <div className="desktop-downloads__hero">
      <span className="desktop-downloads__eyebrow">YOUR EVALUATION WORKSPACE</span>
      <h1>Downloads</h1>
      <p>Take your evaluation workspace to the machine where you work best.</p>
    </div>
    <Card><CardBody>
      <div className="desktop-downloads__intro"><div className="desktop-downloads__icon"><DownloadIcon size={32} /></div>
        <div><span className="desktop-downloads__eyebrow">WINDOWS 64-BIT · PORTABLE</span>
          <h2>Desktop App</h2><p>Listen, respond and evaluate with local or cloud models. Results and recordings sync to your platform.</p>
        </div></div>
      <div className="desktop-downloads__features"><span>No Python installation</span><span>Local &amp; cloud models</span><span>Background sync &amp; retry</span></div>
      {unavailable || !releases.length ? <p role="status">{unavailable ? 'Downloads are temporarily unavailable. Please try again shortly.' : 'The desktop release is being prepared. Please check back shortly.'}</p> :
        <div className="desktop-downloads__options">{releases.map((release) => <div className="desktop-downloads__option" key={release.id}>
          <h3>{release.id === 'desktop-cuda' ? 'GPU portable with models' : release.id === 'desktop-runtime' ? 'App & runtime without models' : 'CPU edition'}</h3>
          <p>{release.id === 'desktop-cuda' ? 'Complete NVIDIA GPU package with Qwen 3.5 4B, Whisper large-v3 and Piper English/Hindi voices. Best for a new installation.' : release.id === 'desktop-runtime' ? 'The executable, application and CPU/NVIDIA runtimes, without model weights or voices. Use your existing models, install models in setup, or use cloud models.' : 'For machines without an NVIDIA GPU. Download local models in setup or use cloud models.'}</p>
          <a className="desktop-downloads__button" href={'/api/downloads?artifact=' + release.id + '&sha256=' + release.sha256}><DownloadIcon size={18} />{release.id === 'desktop-runtime' ? 'Download without models' : 'Download Desktop App'}</a>
          <small>{(release.size_bytes / 1024 / 1024).toFixed(0)} MiB · Windows x64</small>
          <details><summary>File details &amp; SHA-256</summary><p>{release.id === 'desktop-cuda' ? 'Desktop-App-GPU.zip' : release.id === 'desktop-runtime' ? 'Desktop-App.zip' : 'Desktop-App-CPU.zip'}</p><code>{release.sha256}</code></details>
        </div>)}</div>}
      <div className="desktop-downloads__setup"><h3>Ready in three steps</h3><ol>
        <li>Download and extract the ZIP to a folder you can write to.</li>
        <li>Run <strong>Human-test.exe</strong> and enroll this machine with your platform.</li>
        <li>Use the GPU bundle's included models, download other assigned models in setup, or choose cloud models.</li>
      </ol><p>The platform address is preconfigured. Match the device's assigned models to the models installed in the app. Keep the extracted folder together when moving the app.</p>
      <h3>Updating an existing installation</h3><p>Close Human-test and its model services, then extract the smaller ZIP into the parent of your existing Desktop-App-GPU folder and replace the application files. Both downloads use the same folder layout. Keep your models, saved connection and history folders; the smaller ZIP does not contain or replace them. You do not need to enroll again.</p></div>
    </CardBody></Card>
  </div>;
}
