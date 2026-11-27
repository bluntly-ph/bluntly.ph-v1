import "server-only";

import { apiFetch } from "./api/client";

/** A member in people search (GET /users/search). Public fields only. */
export type Person = {
  id: string;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  trust_stage: number;
  trust_level_name: string | null;
  review_count: number;
  is_claimed_seller: boolean;
};

/** People search for the People tab. Public. Null means unreachable. */
export async function searchPeople(q: string, limit = 24): Promise<Person[] | null> {
  const needle = q.trim();
  if (!needle) return [];
  try {
    const params = new URLSearchParams({ q: needle, limit: String(limit) });
    return await apiFetch<Person[]>(`/api/v1/users/search?${params}`);
  } catch {
    return null;
  }
}
