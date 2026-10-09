const config = require("../config");
const labels = {
  location: "住在哪",
  daily: "每天做什么",
  social: "和谁在一起",
  finance: "财务准备",
  health: "健康管理",
};
const dimensions = Object.keys(labels).map((id, i) => ({
  id,
  name: labels[id],
  icon: ["🏡", "☀️", "👥", "💰", "💪"][i],
}));
let loggingIn = null;
function request(path, method = "GET", data = {}, retried = false) {
  const token = wx.getStorageSync("session");
  return wx.cloud
    .callContainer({
      config: { env: config.env },
      path: "/api" + path,
      method,
      data,
      header: {
        "X-WX-SERVICE": config.service,
        "Content-Type": "application/json",
        ...(token ? { Authorization: "Bearer " + token } : {}),
      },
    })
    .then(async (res) => {
      if (res.statusCode === 401 && token && !retried) {
        await login();
        return request(path, method, data, true);
      }
      const body = res.data;
      if (!body || body.code !== 0)
        throw new Error((body && body.errorMsg) || "服务异常，请稍后再试");
      return body.data;
    })
    .catch((error) => {
      throw new Error(error.message || "网络开小差了，请重试");
    });
}
function login() {
  if (loggingIn) return loggingIn;
  loggingIn = new Promise((resolve, reject) =>
    wx.login({ success: resolve, fail: reject }),
  )
    .then((res) => request("/user/login", "POST", { code: res.code }))
    .then((data) => {
      wx.setStorageSync("session", data.token);
      wx.setStorageSync("profile", data.profile);
      return data.profile;
    })
    .finally(() => {
      loggingIn = null;
    });
  return loggingIn;
}
function requireLogin() {
  if (
    wx.getStorageSync("session") &&
    (wx.getStorageSync("profile") || {}).nickname
  )
    return true;
  wx.showModal({
    title: "开始你的退休规划",
    content: "登录并完善资料后，即可保存想法和参与互动。",
    confirmText: "去完善",
    success: (r) => {
      if (r.confirm) wx.navigateTo({ url: "/pages/onboarding/index" });
    },
  });
  return false;
}
function toast(error) {
  wx.showToast({
    title: typeof error === "string" ? error : error.message,
    icon: "none",
    duration: 2500,
  });
}
function confirm(content) {
  return new Promise((resolve) =>
    wx.showModal({
      title: "请确认",
      content,
      success: (r) => resolve(r.confirm),
      fail: () => resolve(false),
    }),
  );
}
function fullUrl(path) {
  return path && path.startsWith("/api/media/") ? config.baseUrl + path : path;
}
function decorate(item) {
  if (item.author)
    item.author = {
      ...item.author,
      avatar_url: fullUrl(item.author.avatar_url),
    };
  if (item.images) item.imageUrls = item.images.map(fullUrl);
  if (item.dimensions)
    item.dimensionLabels = item.dimensions.map((id) => labels[id]);
  item.dimensionName = labels[item.dimension] || "";
  item.date = item.created_at
    ? new Date(item.created_at).toLocaleDateString()
    : "";
  return item;
}
async function upload(path) {
  const fs = wx.getFileSystemManager();
  let file = path;
  for (const quality of [80, 60, 40, 20]) {
    const info = await new Promise((resolve, reject) =>
      fs.getFileInfo({ filePath: file, success: resolve, fail: reject }),
    );
    if (info.size <= 800 * 1024) break;
    file = (
      await new Promise((resolve, reject) =>
        wx.compressImage({
          src: path,
          quality,
          success: resolve,
          fail: reject,
        }),
      )
    ).tempFilePath;
  }
  const info = await new Promise((resolve, reject) =>
    fs.getFileInfo({ filePath: file, success: resolve, fail: reject }),
  );
  if (info.size > 800 * 1024) throw new Error("图片太大，请选择较小的图片");
  const base64 = await new Promise((resolve, reject) =>
    fs.readFile({
      filePath: file,
      encoding: "base64",
      success: (r) => resolve(r.data),
      fail: reject,
    }),
  );
  return (await request("/media", "POST", { base64 })).url;
}
function invalidateBlueprintCache() {
  const profile = wx.getStorageSync("profile");
  if (profile && profile.id) {
    const base = "blueprint:" + profile.id;
    wx.removeStorageSync(base);
    for (const d of dimensions) wx.removeStorageSync(base + ":" + d.id);
  }
}
function logout() {
  invalidateBlueprintCache();
  wx.removeStorageSync("session");
  wx.removeStorageSync("profile");
}
module.exports = {
  request,
  login,
  requireLogin,
  toast,
  confirm,
  dimensions,
  labels,
  decorate,
  fullUrl,
  upload,
  logout,
  invalidateBlueprintCache,
};
