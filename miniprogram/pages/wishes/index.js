const api = require("../../utils/api");
Page({
  data: {
    dimensions: api.dimensions,
    sort: "hot",
    dimension: "",
    items: [],
    page: 1,
    hasMore: true,
    loading: false,
    error: "",
    selected: null,
    people: [],
    peopleCount: 0,
  },
  onShow() {
    if (wx.getStorageSync("wishesShowLatest")) {
      this.setData({ sort: "latest" });
      wx.removeStorageSync("wishesShowLatest");
    }
    this.reload();
  },
  async reload() {
    this.setData({ page: 1, items: [], hasMore: true });
    return this.load();
  },
  async load() {
    if (this.data.loading || !this.data.hasMore) return;
    this.setData({ loading: true, error: "" });
    try {
      const res = await api.request(
        "/wishes?page=" +
          this.data.page +
          "&sort=" +
          this.data.sort +
          "&dimension=" +
          this.data.dimension,
      );
      this.setData({
        items: this.data.items.concat(res.items.map(api.decorate)),
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
    this.setData({
      [e.currentTarget.dataset.key]: e.currentTarget.dataset.value,
    });
    this.reload();
  },
  write() {
    if (api.requireLogin()) wx.navigateTo({ url: "/pages/wish-edit/index" });
  },
  async like(e) {
    if (!api.requireLogin() || this._busy) return;
    this._busy = true;
    try {
      const id = e.currentTarget.dataset.id;
      const w = this.data.items.find((i) => i.id === id) || this.data.selected;
      await api.request("/wishes/" + id + "/like", "POST", { liked: !w.liked });
      await this.reload();
      if (this.data.selected && this.data.selected.id === id)
        this.setData({
          selected: this.data.items.find((i) => i.id === id) || null,
        });
    } catch (err) {
      api.toast(err);
    } finally {
      setTimeout(() => {
        this._busy = false;
      }, 300);
    }
  },
  async people(e) {
    const selected = this.data.items.find(
      (i) => i.id === e.currentTarget.dataset.id,
    );
    try {
      const r = await api.request("/wishes/" + selected.id + "/people");
      this.setData({
        selected,
        people: r.people.map((p) => ({
          ...p,
          avatar_url: api.fullUrl(p.avatar_url),
        })),
        peopleCount: r.count,
      });
    } catch (err) {
      api.toast(err);
    }
  },
  close() {
    this.setData({ selected: null });
  },
  noop() {},
  collect() {
    if (!api.requireLogin()) return;
    const wish = this.data.selected;
    wx.showActionSheet({
      itemList: api.dimensions.map((d) => d.icon + " " + d.name),
      success: async (r) => {
        try {
          await api.request("/blueprint/item", "POST", {
            dimension: api.dimensions[r.tapIndex].id,
            content: wish.content,
            tags: [],
          });
          api.toast("已加入蓝图");
          this.close();
        } catch (e) {
          api.toast(e);
        }
      },
    });
  },
  onReachBottom() {
    this.load();
  },
  onPullDownRefresh() {
    this.reload().finally(() => wx.stopPullDownRefresh());
  },
  onShareAppMessage() {
    return { title: "写下你最想要的退休生活", path: "/pages/wishes/index" };
  },
});
