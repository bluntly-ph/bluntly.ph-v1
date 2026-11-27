/**
 * The BFF's signed client IP (QA 2026-09-29, vote-farming network signal).
 *
 * A vote from the site reaches the API through the BFF (`app/api/bff`), so the
 * API sees the BFF's own address, not the voter's. The BFF received the
 * voter's address from the Vercel edge, which sets `x-vercel-forwarded-for`
 * and overwrites `X-Forwarded-For`, so it forwards that address signed:
 * HMAC-SHA256 of `ip|unix seconds` under CLIENT_IP_SIGNING_SECRET, which the
 * API checks (`backend/app/core/client_ip.py`, the same construction). The API
 * keeps only a keyed hash of the network, never the address.
 *
 * Pure and dependency-free apart from node:crypto, so it is unit-tested
 * against the Python implementation (tests/frontend/client-ip-signature.test.mjs).
 */

import { createHmac } from "node:crypto";

export const SIGNED_IP = "x-bluntly-client-ip";
export const SIGNATURE = "x-bluntly-client-ip-signature";
export const SIGNED_AT = "x-bluntly-client-ip-at";
export const VIA_BFF = "x-bluntly-bff";

/** Headers only the BFF may set: dropped from whatever the browser sent. */
export const BFF_ONLY_HEADERS = [SIGNED_IP, SIGNATURE, SIGNED_AT, VIA_BFF];

export function signClientIp(ip: string, at: number, secret: string): string {
  return createHmac("sha256", secret).update(`${ip}|${at}`).digest("hex");
}

/** The three signed-address headers for one forwarded call. */
export function signedClientIpHeaders(
  ip: string,
  secret: string,
  at: number = Math.floor(Date.now() / 1000),
): Record<string, string> {
  return {
    [SIGNED_IP]: ip,
    [SIGNED_AT]: String(at),
    [SIGNATURE]: signClientIp(ip, at, secret),
  };
}

const IPV4 = /^(\d{1,3})(\.\d{1,3}){3}$/;
const IPV6 = /^[0-9a-f:.]+$/i;

/**
 * The voter's address as the Vercel edge reported it, or null. Read only on
 * Vercel: anywhere else these headers are whatever the client wrote.
 */
export function edgeClientIp(headers: Headers, onVercel: boolean): string | null {
  if (!onVercel) return null;
  const raw = (headers.get("x-vercel-forwarded-for") ?? headers.get("x-forwarded-for") ?? "")
    .split(",")[0]
    .trim();
  if (!raw) return null;
  if (IPV4.test(raw) && raw.split(".").every((part) => Number(part) <= 255)) return raw;
  if (raw.includes(":") && IPV6.test(raw)) return raw;
  return null;
}
