const api = require("../../utils/api");
Page({
  data: { profile: null, info: {}, avatar: "" },
  onShow() {
    this.reload();
  },
  async reload() {
    try {
      const profile = wx.getStorageSync("profile") || {};
      this.setData({ profile, avatar: api.fullUrl(profile.avatar_url) });
      if (!wx.getStorageSync("session")) return;
      const info = await api.request("/home");
      this.setData({
        info,
        profile: info.profile,
        avatar: api.fullUrl(info.profile.avatar_url),
      });
    } catch (e) {
      api.toast(e);
    }
  },
  edit() {
    wx.navigateTo({ url: "/pages/onboarding/index" });
  },
  blueprint() {
    if (api.requireLogin()) wx.navigateTo({ url: "/pages/blueprint/index" });
  },
  records(e) {
    if (api.requireLogin())
      wx.navigateTo({
        url: "/pages/records/index?kind=" + e.currentTarget.dataset.kind,
      });
  },
  settings() {
    if (api.requireLogin()) wx.navigateTo({ url: "/pages/settings/index" });
  },
  about() {
    wx.navigateTo({ url: "/pages/about/index" });
  },
  async logout() {
    if (await api.confirm("确认退出登录？")) {
      api.logout();
      this.setData({ profile: null, info: {}, avatar: "" });
    }
  },
});
