const api = require("../../utils/api");
const social = require("../../utils/social");
Page({
  data: {
    id: "",
    profile: {},
    posts: [],
    wishes: [],
    tab: "posts",
    error: "",
    loading: true,
    postPage: 2,
    wishPage: 2,
    postMore: false,
    wishMore: false,
  },
  ...social(),
  onLoad(o) {
    this.setData({ id: o.id });
  },
  onShow() {
    this.reload();
  },
  async reload() {
    this.setData({ loading: true, error: "" });
    try {
      const r = await api.request("/users/" + this.data.id);
      this.setData({
        profile: {
          ...r.profile,
          avatar_url: api.fullUrl(r.profile.avatar_url),
        },
        posts: r.posts.map(api.decorate),
        wishes: r.wishes.map(api.decorate),
        postPage: 2,
        wishPage: 2,
        postMore: r.profile.post_count > 20,
        wishMore: r.profile.wish_count > 20,
      });
    } catch (e) {
      this.setData({ error: e.message });
    } finally {
      this.setData({ loading: false });
    }
  },
  tab(e) {
    this.setData({ tab: e.currentTarget.dataset.id });
  },
  async onReachBottom() {
    if (this._moreBusy) return;
    const isPost = this.data.tab === "posts";
    if (!(isPost ? this.data.postMore : this.data.wishMore)) return;
    this._moreBusy = true;
    try {
      const page = isPost ? this.data.postPage : this.data.wishPage;
      const r = await api.request(
        "/" +
          (isPost ? "posts" : "wishes") +
          "?author=" +
          this.data.id +
          "&page=" +
          page,
      );
      this.setData({
        [isPost ? "posts" : "wishes"]: (isPost
          ? this.data.posts
          : this.data.wishes
        ).concat(r.items.map(api.decorate)),
        [isPost ? "postPage" : "wishPage"]: page + 1,
        [isPost ? "postMore" : "wishMore"]: r.has_more,
      });
    } catch (e) {
      api.toast(e);
    } finally {
      this._moreBusy = false;
    }
  },
});
