const api = require("../../utils/api");
const social = require("../../utils/social");
Page({
  data: {
    id: "",
    post: null,
    comments: [],
    page: 1,
    hasMore: true,
    loading: false,
    error: "",
    input: "",
    reply: null,
    sending: false,
    showAll: false,
  },
  ...social(),
  onLoad(o) {
    this.setData({ id: o.id });
    wx.showShareMenu({ menus: ["shareAppMessage"] });
  },
  onShow() {
    this.reload();
  },
  async reload() {
    this.setData({
      loading: true,
      error: "",
      comments: [],
      page: 1,
      hasMore: true,
      showAll: false,
    });
    try {
      const post = api.decorate(await api.request("/posts/" + this.data.id));
      this.setData({ post });
      await this.loadComments();
    } catch (e) {
      this.setData({ error: e.message });
    } finally {
      this.setData({ loading: false });
    }
  },
  async loadComments() {
    if (!this.data.hasMore || this._commentsBusy) return;
    this._commentsBusy = true;
    try {
      const res = await api.request(
        "/posts/" +
          this.data.id +
          "/comments?page=" +
          this.data.page +
          (this.data.showAll ? "" : "&preview=1"),
      );
      this.setData({
        comments: this.data.comments.concat(res.items.map(api.decorate)),
        page: this.data.page + 1,
        hasMore: res.has_more,
      });
    } catch (e) {
      api.toast(e);
    } finally {
      this._commentsBusy = false;
    }
  },
  allComments() {
    this.setData({ comments: [], page: 1, hasMore: true, showAll: true });
    this.loadComments();
  },
  async like() {
    if (!api.requireLogin() || this._likeBusy) return;
    this._likeBusy = true;
    try {
      const p = this.data.post;
      const r = await api.request("/posts/" + p.id + "/like", "POST", {
        liked: !p.liked,
      });
      this.setData({ "post.liked": r.liked, "post.like_count": r.like_count });
    } catch (e) {
      api.toast(e);
    } finally {
      setTimeout(() => {
        this._likeBusy = false;
      }, 300);
    }
  },
  collect() {
    this.collectPost({ detail: { post: this.data.post } });
  },
  author() {
    this.openAuthor({ detail: { id: this.data.post.author.id } });
  },
  input(e) {
    this.setData({ input: e.detail.value });
  },
  reply(e) {
    if (!api.requireLogin()) return;
    const c = this.data.comments.find(
      (i) => i.id === e.currentTarget.dataset.id,
    );
    this.setData({ reply: c, input: "" });
  },
  clearReply() {
    this.setData({ reply: null });
  },
  async send() {
    if (this.data.sending || !api.requireLogin()) return;
    this.setData({ sending: true });
    try {
      await api.request("/posts/" + this.data.id + "/comments", "POST", {
        content: this.data.input,
        parent_id: this.data.reply ? this.data.reply.id : null,
      });
      this.setData({ input: "", reply: null });
      api.toast("评论已发布");
      await this.reload();
    } catch (e) {
      api.toast(e);
    } finally {
      this.setData({ sending: false, showAll: false });
    }
  },
  async commentLike(e) {
    if (!api.requireLogin() || this._commentLikeBusy) return;
    this._commentLikeBusy = true;
    try {
      const id = e.currentTarget.dataset.id;
      const i = this.data.comments.findIndex((c) => c.id === id);
      const r = await api.request("/comments/" + id + "/like", "POST", {
        liked: !this.data.comments[i].liked,
      });
      this.setData({
        ["comments[" + i + "].liked"]: r.liked,
        ["comments[" + i + "].like_count"]: r.like_count,
      });
    } catch (err) {
      api.toast(err);
    } finally {
      setTimeout(() => {
        this._commentLikeBusy = false;
      }, 300);
    }
  },
  preview(e) {
    wx.previewImage({
      current: e.currentTarget.dataset.url,
      urls: this.data.post.imageUrls,
    });
  },
  menu() {
    const p = this.data.post;
    wx.showActionSheet({
      itemList: p.mine ? ["编辑", "删除"] : ["举报"],
      success: async (r) => {
        if (p.mine && r.tapIndex === 0) {
          wx.navigateTo({
            url: "/pages/publish/index?id=" + p.id,
            success: (s) => s.eventChannel.emit("post", p),
          });
          return;
        }
        if (p.mine) {
          if (await api.confirm("确认删除这条生活分享？")) {
            try {
              await api.request("/posts/" + p.id, "DELETE", {});
              api.toast("已删除");
              wx.navigateBack();
            } catch (e) {
              api.toast(e);
            }
          }
        } else this.report();
      },
    });
  },
  report() {
    if (!api.requireLogin()) return;
    const reasons = [
      "内容不实或误导",
      "广告或营销内容",
      "不雅或令人不适",
      "其他",
    ];
    wx.showActionSheet({
      itemList: reasons,
      success: async (r) => {
        try {
          await api.request("/posts/" + this.data.id + "/report", "POST", {
            reason: reasons[r.tapIndex],
          });
          api.toast("感谢反馈，我们已收到举报");
        } catch (e) {
          api.toast(e);
        }
      },
    });
  },
  onReachBottom() {
    if (this.data.showAll) this.loadComments();
  },
  onPullDownRefresh() {
    this.reload().finally(() => wx.stopPullDownRefresh());
  },
  onShareAppMessage() {
    return {
      title: this.data.post
        ? this.data.post.content.slice(0, 40)
        : "一段退休生活灵感",
      path: "/pages/post/index?id=" + this.data.id,
    };
  },
});
