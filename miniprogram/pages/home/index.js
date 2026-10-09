const api = require("../../utils/api");
const social = require("../../utils/social");
Page({
  data: { loading: true, info: {}, posts: [], greeting: "", error: "" },
  ...social(),
  onShow() {
    this.reload();
  },
  async reload() {
    this.setData({ loading: true, error: "" });
    try {
      const info = await api.request("/home");
      const h = new Date().getHours();
      this.setData({
        info,
        posts: info.recommendations.map(api.decorate),
        greeting:
          h < 6 ? "夜深了" : h < 12 ? "早上好" : h < 18 ? "下午好" : "晚上好",
      });
      if (info.profile) wx.setStorageSync("profile", info.profile);
      if (info.milestone) {
        const m = info.milestone;
        const texts = {
          10: "现在开始规划，正是时候",
          5: "5年倒计时，退休生活清单该具体了",
          3: "3年后你要住在哪里？",
          1: "一年后的第一天，你想做什么？",
        };
        wx.showModal({
          title: "距离退休还有" + m.years + "年",
          content: texts[m.kind],
          confirmText: "去完善",
          cancelText: "知道了",
          success: async (r) => {
            try {
              await api.request("/milestones/" + m.kind + "/ack", "POST", {});
              if (r.confirm) this.blueprint();
            } catch (e) {
              api.toast(e);
            }
          },
        });
      }
    } catch (e) {
      this.setData({ error: e.message });
    } finally {
      this.setData({ loading: false });
    }
  },
  onPullDownRefresh() {
    this.reload().finally(() => wx.stopPullDownRefresh());
  },
  blueprint() {
    if (api.requireLogin()) wx.navigateTo({ url: "/pages/blueprint/index" });
  },
  edit() {
    wx.navigateTo({ url: "/pages/onboarding/index" });
  },
  discover() {
    wx.switchTab({ url: "/pages/discover/index" });
  },
  notifications() {
    if (api.requireLogin())
      wx.navigateTo({ url: "/pages/notifications/index" });
  },
  async dismissAnnual() {
    try {
      await api.request(
        "/milestones/" + this.data.info.annual.kind + "/ack",
        "POST",
        {},
      );
      this.setData({ "info.annual": null });
    } catch (e) {
      api.toast(e);
    }
  },
  onShareAppMessage() {
    return {
      title: "退休不是终点，是新的起点 · 凡事预则立",
      path: "/pages/home/index",
    };
  },
});
