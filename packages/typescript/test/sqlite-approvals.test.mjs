import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import {
  ApprovalManager,
  ApprovalRequiredError,
  SqliteApprovalStore,
} from "../dist/index.js";

const require = createRequire(import.meta.url);
const Database = require("better-sqlite3");

test("approved action survives manager restart and is consumed only once", () => {
  const db = new Database(":memory:");
  const first = new ApprovalManager({ store: new SqliteApprovalStore(db) });
  const action = { order_id: "1042", amount: 2500, currency: "INR" };
  const request = first.request({
    principalId: "finance-user", toolName: "payments.refund",
    summary: "Refund order 1042", action,
  });
  first.approve(request.requestId, "finance-admin");

  const restarted = new ApprovalManager({ store: new SqliteApprovalStore(db) });
  const grant = restarted.consume(request.requestId, "finance-user", "payments.refund", action);
  assert.equal(grant.approverId, "finance-admin");
  assert.throws(
    () => new ApprovalManager({ store: new SqliteApprovalStore(db) })
      .consume(request.requestId, "finance-user", "payments.refund", action),
    ApprovalRequiredError,
  );
  db.close();
});

test("two manager instances cannot consume the same approval", () => {
  const db = new Database(":memory:");
  const setup = new ApprovalManager({ store: new SqliteApprovalStore(db) });
  const request = setup.request({
    principalId: "user-17", toolName: "files.delete", summary: "Delete archive",
  });
  setup.approve(request.requestId, "admin-1");
  const first = new ApprovalManager({ store: new SqliteApprovalStore(db) });
  const second = new ApprovalManager({ store: new SqliteApprovalStore(db) });
  first.consume(request.requestId, "user-17", "files.delete");
  assert.throws(
    () => second.consume(request.requestId, "user-17", "files.delete"),
    ApprovalRequiredError,
  );
  db.close();
});

test("expiry is applied after constructing a new manager over the same database", () => {
  const db = new Database(":memory:");
  let now = 100_000;
  const first = new ApprovalManager({
    clock: () => now, store: new SqliteApprovalStore(db),
  });
  const request = first.request({
    principalId: "user-17", toolName: "files.delete",
    summary: "Delete archive", ttlSeconds: 5,
  });
  now = 106_000;
  const restarted = new ApprovalManager({
    clock: () => now, store: new SqliteApprovalStore(db),
  });
  assert.equal(restarted.get(request.requestId).status, "expired");
  db.close();
});
