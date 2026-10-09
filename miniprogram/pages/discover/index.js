const api = require("../../utils/api");
const social = require("../../utils/social");
Page({
  data: {
    dimensions: api.dimensions,
    dimension: "",
    posts: [],
    page: 1,
    hasMore: true,
    loading: false,
    error: "",
  },
  ...social(),
  onShow() {
    this.reload();
  },
  async reload() {
    this.setData({ page: 1, posts: [], hasMore: true });
    return this.load();
  },
  async load() {
    if (this.data.loading || !this.data.hasMore) return;
    this.setData({ loading: true, error: "" });
    const dimension = this.data.dimension;
    try {
      const res = await api.request(
        "/posts?page=" + this.data.page + "&dimension=" + dimension,
      );
      if (dimension !== this.data.dimension) return;
      this.setData({
        posts: this.data.posts.concat(res.items.map(api.decorate)),
        page: this.data.page + 1,
        hasMore: res.has_more,
      });
    } catch (e) {
      this.setData({ error: e.message });
    } finally {
      this.setData({ loading: false });
    }
  },
  filter(e) {
    if (this.data.loading) return;
    this.setData({ dimension: e.currentTarget.dataset.id });
    this.reload();
  },
  publish() {
    if (api.requireLogin()) wx.navigateTo({ url: "/pages/publish/index" });
  },
  onReachBottom() {
    this.load();
  },
  onPullDownRefresh() {
    this.reload().finally(() => wx.stopPullDownRefresh());
  },
  onShareAppMessage() {
    return { title: "看看他们如何过退休生活", path: "/pages/discover/index" };
  },
});
