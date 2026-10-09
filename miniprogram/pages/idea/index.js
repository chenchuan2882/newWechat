const api = require("../../utils/api");
Page({
  data: {
    dimensions: api.dimensions,
    dimIndex: 0,
    content: "",
    tags: "",
    id: "",
    saving: false,
  },
  onLoad(o) {
    if (o.dimension)
      this.setData({
        dimIndex: api.dimensions.findIndex((d) => d.id === o.dimension),
      });
    if (o.id) {
      this.setData({ id: o.id });
      this.getOpenerEventChannel().on("item", (item) =>
        this.setData({
          dimIndex: api.dimensions.findIndex((d) => d.id === item.dimension),
          content: item.content,
          tags: item.tags.join(" "),
        }),
      );
    }
  },
  input(e) {
    this.setData({ [e.currentTarget.dataset.key]: e.detail.value });
  },
  pick(e) {
    this.setData({ dimIndex: Number(e.detail.value) });
  },
  async save() {
    if (this.data.saving || !api.requireLogin()) return;
    this.setData({ saving: true });
    try {
      const d = this.data;
      await api.request(
        "/blueprint/item" + (d.id ? "/" + d.id : ""),
        d.id ? "PUT" : "POST",
        {
          dimension: api.dimensions[d.dimIndex].id,
          content: d.content,
          tags: d.tags.trim() ? d.tags.trim().split(/\s+/) : [],
        },
      );
      api.invalidateBlueprintCache();
      api.toast("想法已保存");
      wx.navigateBack();
    } catch (e) {
      api.toast(e);
    } finally {
      this.setData({ saving: false });
    }
  },
});
