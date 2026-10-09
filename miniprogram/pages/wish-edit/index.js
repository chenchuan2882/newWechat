const api = require("../../utils/api");
Page({
  data: {
    dimensions: api.dimensions,
    dimension: "",
    content: "",
    saving: false,
    remaining: 0,
    loaded: false,
  },
  async onLoad() {
    try {
      const q = await api.request("/wishes/quota");
      this.setData({ remaining: q.remaining, loaded: true });
    } catch (e) {
      api.toast(e);
    }
  },
  input(e) {
    this.setData({ content: e.detail.value });
  },
  dimension(e) {
    const id = e.currentTarget.dataset.id;
    this.setData({ dimension: this.data.dimension === id ? "" : id });
  },
  async save() {
    if (this.data.saving || !api.requireLogin()) return;
    this.setData({ saving: true });
    try {
      await api.request("/wishes", "POST", {
        content: this.data.content,
        dimension: this.data.dimension || null,
      });
      wx.setStorageSync("wishesShowLatest", true);
      api.toast("愿望已写下");
      wx.navigateBack();
    } catch (e) {
      api.toast(e);
    } finally {
      this.setData({ saving: false });
    }
  },
});
