const api = require("../../utils/api");
Page({
  data: { items: [], saving: false },
  async onLoad() {
    try {
      const p = await api.request("/user/profile");
      const c = await api.request("/config");
      this._templates = c.subscription_templates;
      this.setData({
        items: Object.entries({
          milestone: "里程碑提醒",
          annual: "年度蓝图回顾",
          collection: "收藏互动通知",
          comment: "评论通知",
          wish: "愿望 +1 通知",
        }).map(([id, name]) => ({ id, name, enabled: p.settings[id] })),
      });
    } catch (e) {
      api.toast(e);
    }
  },
  async change(e) {
    if (this.data.saving) return;
    const key = e.currentTarget.dataset.id;
    const enabled = e.detail.value;
    this.setData({ saving: true });
    try {
      if (enabled && this._templates[key]) {
        const id = this._templates[key];
        const consent = await new Promise((resolve, reject) =>
          wx.requestSubscribeMessage({
            tmplIds: [id],
            success: resolve,
            fail: reject,
          }),
        );
        if (consent[id] === "accept")
          await api.request("/user/subscriptions", "POST", {
            kind: key,
            template_id: id,
          });
      }
      await api.request("/user/settings", "PUT", { [key]: enabled });
      this.setData({
        items: this.data.items.map((i) =>
          i.id === key ? { ...i, enabled } : i,
        ),
      });
    } catch (err) {
      api.toast(err);
    } finally {
      this.setData({ saving: false });
    }
  },
});
