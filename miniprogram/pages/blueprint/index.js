const api = require("../../utils/api");
Page({
  data: {
    dimensions: api.dimensions,
    dimension: "",
    items: [],
    counts: {},
    complete: 0,
    total: 0,
    page: 1,
    hasMore: true,
    loading: false,
    error: "",
    offline: false,
  },
  onLoad(o) {
    if (o.dimension) this.setData({ dimension: o.dimension });
  },
  onShow() {
    if (api.requireLogin()) this.reload();
  },
  async reload() {
    this.setData({
      page: 1,
      items: [],
      hasMore: true,
      error: "",
      offline: false,
    });
    try {
      const home = await api.request("/home");
      this.setData({
        counts: home.counts,
        complete: home.complete,
        total: home.total,
      });
    } catch (e) {}
    return this.load();
  },
  async load() {
    if (this.data.loading || !this.data.hasMore) return;
    this.setData({ loading: true });
    const profile = wx.getStorageSync("profile");
    try {
      const result = await api.request(
        "/blueprint/list?page=" +
          this.data.page +
          "&dimension=" +
          this.data.dimension,
      );
      const items = this.data.items.concat(result.items.map(api.decorate));
      this.setData({
        items,
        page: this.data.page + 1,
        hasMore: result.has_more,
        offline: false,
      });
      wx.setStorageSync(
        "blueprint:" +
          profile.id +
          (this.data.dimension ? ":" + this.data.dimension : ""),
        items,
      );
    } catch (e) {
      const cached =
        wx.getStorageSync(
          "blueprint:" +
            profile.id +
            (this.data.dimension ? ":" + this.data.dimension : ""),
        ) || wx.getStorageSync("blueprint:" + profile.id);
      if (cached && cached.length)
        this.setData({
          items: cached.filter(
            (i) => !this.data.dimension || i.dimension === this.data.dimension,
          ),
          offline: true,
          error: "离线浏览已缓存蓝图，恢复网络后可编辑",
        });
      else this.setData({ error: e.message });
    } finally {
      this.setData({ loading: false });
    }
  },
  filter(e) {
    if (this.data.loading) return;
    this.setData({ dimension: e.currentTarget.dataset.id });
    this.reload();
  },
  add() {
    if (this.data.offline) {
      api.toast("请连接网络后编辑");
      return;
    }
    wx.navigateTo({
      url: "/pages/idea/index?dimension=" + this.data.dimension,
    });
  },
  edit(e) {
    if (this.data.offline) return;
    const item = this.data.items.find(
      (i) => i.id === e.currentTarget.dataset.id,
    );
    wx.navigateTo({
      url: "/pages/idea/index?id=" + item.id,
      success: (r) => r.eventChannel.emit("item", item),
    });
  },
  async remove(e) {
    if (this.data.offline) return;
    if (await api.confirm("确认删除这条想法？")) {
      try {
        await api.request(
          "/blueprint/item/" + e.currentTarget.dataset.id,
          "DELETE",
          {},
        );
        api.invalidateBlueprintCache();
        api.toast("已删除");
        this.reload();
      } catch (err) {
        api.toast(err);
      }
    }
  },
  discover() {
    wx.switchTab({ url: "/pages/discover/index" });
  },
  onReachBottom() {
    if (!this.data.offline) this.load();
  },
  onPullDownRefresh() {
    this.reload().finally(() => wx.stopPullDownRefresh());
  },
});
