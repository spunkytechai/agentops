import test from "node:test";
import assert from "node:assert/strict";
import {
  ApprovalDeniedError,
  ApprovalManager,
  ApprovalRequiredError,
} from "../dist/index.js";

test("approved request is bound and can be consumed only once", () => {
  const manager = new ApprovalManager();
  const request = manager.request({
    principalId: "user-17",
    toolName: "payments.refund",
    summary: "Refund order 1042",
  });
  manager.approve(request.requestId, "admin-1");
  const grant = manager.consume(request.requestId, "user-17", "payments.refund");
  assert.equal(grant.requestId, request.requestId);
  assert.equal(grant.approverId, "admin-1");
  assert.throws(
    () => manager.consume(request.requestId, "user-17", "payments.refund"),
    ApprovalRequiredError,
  );
});

test("pending and denied requests cannot be consumed", () => {
  const manager = new ApprovalManager();
  const pending = manager.request({ principalId: "user-17", toolName: "files.delete", summary: "Delete archive" });
  assert.throws(() => manager.consume(pending.requestId, "user-17", "files.delete"), ApprovalRequiredError);

  const denied = manager.request({ principalId: "user-17", toolName: "files.delete", summary: "Delete archive" });
  manager.deny(denied.requestId, "admin-1", "Retention policy");
  assert.throws(() => manager.consume(denied.requestId, "user-17", "files.delete"), ApprovalDeniedError);
});

test("approval is bound to exact principal and tool", () => {
  const manager = new ApprovalManager();
  const request = manager.request({ principalId: "user-17", toolName: "payments.refund", summary: "Refund order 1042" });
  manager.approve(request.requestId, "admin-1");
  assert.throws(() => manager.consume(request.requestId, "user-18", "payments.refund"), ApprovalRequiredError);
  assert.throws(() => manager.consume(request.requestId, "user-17", "payments.capture"), ApprovalRequiredError);
});

test("expired approval cannot be consumed", () => {
  let now = 100;
  const manager = new ApprovalManager({ clock: () => now });
  const request = manager.request({
    principalId: "user-17",
    toolName: "payments.refund",
    summary: "Refund order 1042",
    ttlSeconds: 10,
  });
  manager.approve(request.requestId, "admin-1");
  now = 111;
  assert.throws(() => manager.consume(request.requestId, "user-17", "payments.refund"), ApprovalRequiredError);
});

test("only pending requests can be decided and inputs are validated", () => {
  const manager = new ApprovalManager();
  const request = manager.request({ principalId: "user-17", toolName: "files.delete", summary: "Delete archive" });
  manager.deny(request.requestId, "admin-1", "No");
  assert.throws(() => manager.approve(request.requestId, "admin-2"), ApprovalDeniedError);
  assert.throws(() => manager.request({ principalId: " ", toolName: "files.delete", summary: "Delete" }), TypeError);
  assert.throws(() => manager.request({ principalId: "user-17", toolName: "files.delete", summary: " " }), TypeError);
  assert.throws(() => manager.request({ principalId: "user-17", toolName: "files.delete", summary: "Delete", ttlSeconds: 0 }), RangeError);
});
