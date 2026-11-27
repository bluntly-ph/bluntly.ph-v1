/**
 * Member roles (owner decisions B-D, 2026-09-28). Pure; safe on the client.
 *
 * There is no administrator role. An Administrator runs the operational queues;
 * a Super Admin does everything an Administrator does, plus user management
 * and the 2.5-star routing decision. The API enforces every one of these —
 * the UI only decides what to offer.
 */

export type MemberRole = "user" | "seller" | "administrator" | "super_admin";

export const ROLE_LABEL: Record<MemberRole, string> = {
  user: "Member",
  seller: "Seller",
  administrator: "Administrator",
  super_admin: "Super Admin",
};

/** Administrator or Super Admin. */
export function isStaffRole(role: string | null | undefined): boolean {
  return role === "administrator" || role === "super_admin";
}

export function isSuperAdminRole(role: string | null | undefined): boolean {
  return role === "super_admin";
}

export function roleLabel(role: string | null | undefined): string {
  return (role && ROLE_LABEL[role as MemberRole]) || "Member";
}
