// Structural verification plus executable tests for the shared network client.
const fs = require("node:fs");
const path = require("node:path");
const cp = require("node:child_process");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const root = path.join(__dirname, "../miniprogram");
function files(dir) {
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .flatMap((f) =>
      f.isDirectory()
        ? files(path.join(dir, f.name))
        : [path.join(dir, f.name)],
    );
}
const app = JSON.parse(fs.readFileSync(path.join(root, "app.json"), "utf8"));
assert.equal(app.tabBar.list.length, 4);
for (const page of app.pages) {
  for (const ext of ["js", "json", "wxml", "wxss"])
    assert.ok(
      fs.existsSync(path.join(root, page + "." + ext)),
      page + "." + ext,
    );
}
for (const file of files(root)) {
  if (file.endsWith(".json")) JSON.parse(fs.readFileSync(file, "utf8"));
  if (file.endsWith(".js"))
    cp.execFileSync(process.execPath, ["--check", file]);
}
let loggedCalls = [];
const store = new Map();
let failOnce = false;
const wx = {
  getStorageSync: (k) => store.get(k) || "",
  setStorageSync: (k, v) => store.set(k, v),
  removeStorageSync: (k) => store.delete(k),
  login: (o) => o.success({ code: "fresh-code" }),
  showToast: () => {},
  showModal: () => {},
  cloud: {
    callContainer: async (o) => {
      loggedCalls.push(o);
      if (o.path === "/api/user/login")
        return {
          statusCode: 200,
          data: {
            code: 0,
            data: {
              token: "new-token",
              profile: { id: "user-id", nickname: "规划用户" },
            },
          },
        };
      if (failOnce) {
        failOnce = false;
        return { statusCode: 401, data: { code: -1, errorMsg: "expired" } };
      }
      return { statusCode: 200, data: { code: 0, data: { ok: true } } };
    },
  },
};
const moduleObject = { exports: {} };
const context = {
  wx,
  module: moduleObject,
  require: (p) => require(path.resolve(root, "utils", p)),
  setTimeout,
  console,
};
vm.runInNewContext(
  fs.readFileSync(path.join(root, "utils/api.js"), "utf8"),
  context,
);
const api = moduleObject.exports;
(async () => {
  await api.request("/posts");
  assert.equal(loggedCalls[0].header.Authorization, undefined);
  assert.equal(loggedCalls[0].header["X-WX-SERVICE"], "flask-0zs5");
  assert.equal(loggedCalls[0].config.env, "prod-d5gjoz9hoc91797d2");
  store.set("session", "expired-token");
  failOnce = true;
  await api.request("/blueprint/list");
  assert.equal(loggedCalls.at(-1).header.Authorization, "Bearer new-token");
  assert.equal(
    loggedCalls.filter((c) => c.path === "/api/user/login").length,
    1,
  );
  assert.ok(!JSON.stringify(loggedCalls).includes("openid"));
  store.set("blueprint:user-id", [{ content: "私有蓝图" }]);
  api.logout();
  assert.equal(store.has("session"), false);
  assert.equal(store.has("blueprint:user-id"), false);
  assert.ok(api.fullUrl("/api/media/abc").startsWith("https://flask-"));
  console.log(
    "Mini-program: page structure, JSON, JavaScript syntax, auth renewal and logout cache checks passed.",
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
