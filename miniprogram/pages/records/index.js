const api = require("../../utils/api");
const social = require("../../utils/social");
Page({
  data: {
    kind: "posts",
    status: "published",
    posts: [],
    items: [],
    page: 1,
    hasMore: true,
    loading: false,
    error: "",
  },
  ...social(),
  onLoad(o) {
    this.setData({ kind: o.kind || "posts" });
    wx.setNavigationBarTitle({
      title: { posts: "我的发布", collected: "我的收藏", wishes: "我的愿望" }[
        this.data.kind
      ],
    });
  },
  onShow() {
    this.reload();
  },
  async reload() {
    this.setData({ page: 1, posts: [], items: [], hasMore: true });
    return this.load();
  },
  async load() {
    if (this.data.loading || !this.data.hasMore) return;
    this.setData({ loading: true, error: "" });
    try {
      const kind = this.data.kind;
      const path =
        kind === "posts"
          ? "/posts?mine=1&status=" + this.data.status
          : kind === "wishes"
            ? "/wishes?mine=1"
            : "/blueprint/list?collected=1";
      const r = await api.request(path + "&page=" + this.data.page);
      this.setData({
        [kind === "posts" ? "posts" : "items"]: (kind === "posts"
          ? this.data.posts
          : this.data.items
        ).concat(r.items.map(api.decorate)),
        page: this.data.page + 1,
        hasMore: r.has_more,
      });
    } catch (e) {
      this.setData({ error: e.message });
    } finally {
      this.setData({ loading: false });
    }
  },
  status(e) {
    if (this.data.loading) return;
    this.setData({ status: e.currentTarget.dataset.id });
    this.reload();
  },
  async remove(e) {
    const type = this.data.kind === "wishes" ? "wishes" : "posts";
    if (
      await api.confirm(
        "确认删除这条" + (type === "wishes" ? "愿望" : "生活分享") + "？",
      )
    ) {
      try {
        await api.request(
          "/" + type + "/" + e.currentTarget.dataset.id,
          "DELETE",
          {},
        );
        api.toast("已删除");
        this.reload();
      } catch (err) {
        api.toast(err);
      }
    }
  },
  editPost(e) {
    const p = this.data.posts.find((i) => i.id === e.currentTarget.dataset.id);
    wx.navigateTo({
      url: "/pages/publish/index?id=" + p.id,
      success: (r) => r.eventChannel.emit("post", p),
    });
  },
  blueprint(e) {
    wx.navigateTo({
      url: "/pages/blueprint/index?dimension=" + e.currentTarget.dataset.id,
    });
  },
  onReachBottom() {
    this.load();
  },
  onPullDownRefresh() {
    this.reload().finally(() => wx.stopPullDownRefresh());
  },
});
