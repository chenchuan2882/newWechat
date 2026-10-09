const api = require("../../utils/api");
Page({
  data: { items: [], page: 1, hasMore: true, loading: false, error: "" },
  onShow() {
    this.reload();
  },
  async reload() {
    this.setData({ items: [], page: 1, hasMore: true });
    return this.load();
  },
  async load() {
    if (this.data.loading || !this.data.hasMore) return;
    this.setData({ loading: true, error: "" });
    try {
      const r = await api.request("/notifications?page=" + this.data.page);
      this.setData({
        items: this.data.items.concat(r.items),
        page: this.data.page + 1,
        hasMore: r.has_more,
      });
      await api.request("/notifications", "PUT", {});
    } catch (e) {
      this.setData({ error: e.message });
    } finally {
      this.setData({ loading: false });
    }
  },
  onReachBottom() {
    this.load();
  },
  onPullDownRefresh() {
    this.reload().finally(() => wx.stopPullDownRefresh());
  },
});
