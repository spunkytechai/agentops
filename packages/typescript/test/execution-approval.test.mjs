import test from "node:test";
import assert from "node:assert/strict";
import {
  ApprovalManager,
  ApprovalRequiredError,
  PolicyDeniedError,
  PolicyRule,
  ToolExecutor,
  ToolPolicy,
} from "../dist/index.js";

const action = { order_id: "1042", amount: 2500, currency: "INR" };

test("approval is bound to canonical action and execution receives that action", async () => {
  const manager = new ApprovalManager();
  const request = manager.request({
    principalId: "finance-user",
    toolName: "payments.refund",
    summary: "Refund order 1042",
    action,
  });
  manager.approve(request.requestId, "finance-admin");
  const executor = new ToolExecutor(new ToolPolicy({
    rules: [new PolicyRule({ principalId: "finance-user", toolName: "payments.refund", effect: "allow" })],
  }));
  const invoked = [];
  const result = await executor.executeApproved(
    "payments.refund",
    async (approvedAction) => { invoked.push(approvedAction); return "refunded"; },
    "approval-run",
    {
      principalId: "finance-user",
      approvalManager: manager,
      approvalRequestId: request.requestId,
      action,
    },
  );
  assert.equal(result, "refunded");
  assert.deepEqual(invoked, [action]);
  assert.equal(manager.get(request.requestId).status, "consumed");
});

test("action substitution is rejected before tool invocation", async () => {
  const manager = new ApprovalManager();
  const request = manager.request({
    principalId: "finance-user", toolName: "payments.refund",
    summary: "Refund order 1042", action,
  });
  manager.approve(request.requestId, "finance-admin");
  const executor = new ToolExecutor(new ToolPolicy({
    rules: [new PolicyRule({ principalId: "finance-user", toolName: "payments.refund", effect: "allow" })],
  }));
  let invoked = false;
  await assert.rejects(
    executor.executeApproved(
      "payments.refund", async () => { invoked = true; }, "substitution-run",
      {
        principalId: "finance-user", approvalManager: manager,
        approvalRequestId: request.requestId,
        action: { ...action, amount: 25000 },
      },
    ),
    ApprovalRequiredError,
  );
  assert.equal(invoked, false);
});

test("policy deny wins and leaves the approval unconsumed", async () => {
  const manager = new ApprovalManager();
  const request = manager.request({
    principalId: "finance-user", toolName: "payments.refund",
    summary: "Refund order 1042", action,
  });
  manager.approve(request.requestId, "finance-admin");
  const executor = new ToolExecutor(new ToolPolicy({
    allowedTools: ["payments.refund"],
    rules: [new PolicyRule({ principalId: "finance-user", toolName: "payments.refund", effect: "deny" })],
  }));
  await assert.rejects(
    executor.executeApproved("payments.refund", async () => "no", "deny-run", {
      principalId: "finance-user", approvalManager: manager,
      approvalRequestId: request.requestId, action,
    }),
    PolicyDeniedError,
  );
  assert.equal(manager.get(request.requestId).status, "approved");
});

test("invalid timeout does not consume an approved action", async () => {
  const manager = new ApprovalManager();
  const request = manager.request({
    principalId: "finance-user", toolName: "payments.refund",
    summary: "Refund order 1042", action,
  });
  manager.approve(request.requestId, "finance-admin");
  const executor = new ToolExecutor(new ToolPolicy({
    rules: [new PolicyRule({ principalId: "finance-user", toolName: "payments.refund", effect: "allow" })],
  }));
  await assert.rejects(
    executor.executeApproved("payments.refund", async () => "no", "bad-timeout", {
      principalId: "finance-user", approvalManager: manager,
      approvalRequestId: request.requestId, action, timeoutMs: 0,
    }),
    /timeoutMs must be a positive finite number/,
  );
  assert.equal(manager.get(request.requestId).status, "approved");
});
