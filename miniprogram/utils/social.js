const api = require("./api");
function handlers() {
  return {
    openPost(e) {
      wx.navigateTo({ url: "/pages/post/index?id=" + e.detail.id });
    },
    openAuthor(e) {
      wx.navigateTo({ url: "/pages/author/index?id=" + e.detail.id });
    },
    async likePost(e) {
      if (!api.requireLogin() || this._reactionBusy) return;
      this._reactionBusy = true;
      try {
        const p = e.detail.post;
        await api.request("/posts/" + p.id + "/like", "POST", {
          liked: !p.liked,
        });
        await this.reload();
      } catch (err) {
        api.toast(err);
      } finally {
        setTimeout(() => {
          this._reactionBusy = false;
        }, 300);
      }
    },
    collectPost(e) {
      const p = e.detail.post;
      if (!api.requireLogin()) return;
      if (p.collected_dimension) {
        wx.navigateTo({
          url: "/pages/blueprint/index?dimension=" + p.collected_dimension,
        });
        return;
      }
      wx.showActionSheet({
        itemList: api.dimensions.map((d) => d.icon + " " + d.name),
        success: async (r) => {
          try {
            const item = await api.request(
              "/posts/" + p.id + "/collect",
              "POST",
              { dimension: api.dimensions[r.tapIndex].id },
            );
            api.toast("已加入「" + api.labels[item.dimension] + "」");
            await this.reload();
          } catch (err) {
            api.toast(err);
          }
        },
      });
    },
  };
}
module.exports = handlers;
