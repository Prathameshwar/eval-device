import { describe, expect, it } from 'vitest';
import { DEMO_DEVICES, DEMO_DEPARTMENTS } from '../src/data/devices';
import {
  retireDevice,
  DEFAULT_DEVICE_QUERY,
  devicePage,
  isDeviceOnline,
  type Device
} from '../src/lib/device-directory';

describe('device directory queries', () => {
  it('searches the whole dataset by name and location with literal, case-insensitive substrings', () => {
    const result = devicePage(DEMO_DEVICES, { ...DEFAULT_DEVICE_QUERY, q: ' simstation ' }, 0);
    expect(result.total).toBeGreaterThan(0);
    expect(result.items.every((row) => row.name.startsWith('SimStation'))).toBe(true);

    const locResult = devicePage(DEMO_DEVICES, { ...DEFAULT_DEVICE_QUERY, q: 'room' }, 0);
    expect(locResult.total).toBeGreaterThan(0);
    expect(locResult.items.every((row) => row.location?.toLowerCase().includes('room'))).toBe(true);
  });

  it('filters by device type', () => {
    const laptops = devicePage(DEMO_DEVICES, { ...DEFAULT_DEVICE_QUERY, device_type: 'laptop' }, 0);
    expect(laptops.total).toBeGreaterThan(0);
    expect(laptops.items.every((row) => row.device_type === 'laptop')).toBe(true);

    const rpi = devicePage(DEMO_DEVICES, { ...DEFAULT_DEVICE_QUERY, device_type: 'raspberry_pi' }, 0);
    expect(rpi.total).toBeGreaterThan(0);
    expect(rpi.items.every((row) => row.device_type === 'raspberry_pi')).toBe(true);
  });

  it('filters by enrollment state and connection status', () => {
    const enrolled = devicePage(DEMO_DEVICES, { ...DEFAULT_DEVICE_QUERY, enrollment_state: 'enrolled' }, 0);
    expect(enrolled.total).toBeGreaterThan(0);
    expect(enrolled.items.every((row) => row.enrollment_state === 'enrolled')).toBe(true);

    // Filter by online
    const onlineResult = devicePage(DEMO_DEVICES, { ...DEFAULT_DEVICE_QUERY, online: true }, 0);
    expect(onlineResult.items.every((row) => isDeviceOnline(row, '2026-09-22T10:15:00.000Z'))).toBe(true);

    // Filter by offline
    const offlineResult = devicePage(DEMO_DEVICES, { ...DEFAULT_DEVICE_QUERY, online: false }, 0);
    expect(offlineResult.items.every((row) => !isDeviceOnline(row, '2026-09-22T10:15:00.000Z'))).toBe(true);
  });

  it('walks all matching rows without duplicates, in stable order', () => {
    const query = { ...DEFAULT_DEVICE_QUERY };
    const result = devicePage(DEMO_DEVICES, query, 0);
    const ids = result.items.map((row) => row.id);
    expect(ids).toHaveLength(result.items.length);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('uses ID as a tie-breaker', () => {
    const a = { ...DEMO_DEVICES[0]!, name: 'Same device name' };
    const b = { ...DEMO_DEVICES[1]!, name: 'Same device name' };
    const rows = [b, a];
    const sorted = devicePage(rows, DEFAULT_DEVICE_QUERY, 0).items;
    expect(sorted.map((row) => row.id)).toEqual([a.id, b.id]);
  });

  it('retires locally, marks inactive, and preserves the record', () => {
    const device = DEMO_DEVICES[0]!;
    expect(device.enrollment_state).not.toBe('retired');
    const retired = retireDevice(device, '2026-09-22T12:00:00Z');
    expect(retired.enrollment_state).toBe('retired');
    expect(retired.is_active).toBe(false);
    expect(retired.management_version).toBe((device.management_version ?? 0) + 1);

    const doublyRetired = retireDevice(retired, '2026-09-23T00:00:00Z');
    expect(doublyRetired).toBe(retired); // should not re-retire
  });
});
