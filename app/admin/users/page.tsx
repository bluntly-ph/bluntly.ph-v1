import type { Metadata } from "next";

import { SuperAdminOnly } from "@/components/admin/SuperAdminOnly";
import { UserManagement } from "@/components/admin/UserManagement";
import { getSuperAdminAccess } from "@/lib/dal";

export const metadata: Metadata = { title: "User management — bluntly admin" };

/**
 * User management: the Super Admin's alone (owner decisions C and D). No
 * dedicated Figma frame exists; see docs/ADMIN_FIGMA_PARITY.md.
 */
export default async function UserManagementPage() {
  const { allowed } = await getSuperAdminAccess();
  return allowed ? <UserManagement /> : <SuperAdminOnly what="User management" />;
}
