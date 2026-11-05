import { Skeleton } from '@pms/ui';

export default function ConsoleLoading() {
  return <div className="pms-page">
    <p role="status">Loading page...</p>
    <Skeleton lines={4} />
  </div>;
}
