import assert from "node:assert/strict";
import test from "node:test";

import { adminExportFiles, adminExportHref, exportPeriodLabel } from "../../components/admin/export/admin-export-model.ts";

test("file count: earnings is five tables, the rest one each", () => {
  assert.equal(adminExportFiles(["activity", "moderation"]), "2 files");
  assert.equal(adminExportFiles(["earnings"]), "5 files");
  assert.equal(adminExportFiles(["analytics"]), "1 file");
  assert.equal(adminExportFiles([]), "0 files");
});

test("download URL keeps the overlay's order and the period", () => {
  assert.equal(adminExportHref(["analytics", "activity"], "90d"), "/api/bff/api/v1/admin/export?include=activity,analytics&period=90d");
  assert.equal(exportPeriodLabel("12m"), "Last 12 months");
  assert.equal(exportPeriodLabel("nope"), "Last 30 days");
});
