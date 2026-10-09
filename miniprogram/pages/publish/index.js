const api = require("../../utils/api");
Page({
  data: {
    dimensions: api.dimensions.map((d) => ({ ...d, selected: false })),
    content: "",
    customTags: "",
    expense: "",
    images: [],
    saving: false,
    id: "",
  },
  onLoad(o) {
    if (o.id) {
      this.setData({ id: o.id });
      this.getOpenerEventChannel().on("post", (p) =>
        this.setData({
          content: p.content,
          customTags: p.custom_tags.join(" "),
          expense: p.expense_note,
          images: p.images.map((url) => ({ url, preview: api.fullUrl(url) })),
          dimensions: api.dimensions.map((d) => ({
            ...d,
            selected: p.dimensions.includes(d.id),
          })),
        }),
      );
    }
  },
  startDrag(e) {
    this._drag = {
      index: e.currentTarget.dataset.index,
      start: e.touches[0].clientX,
      offset: 0,
    };
  },
  drag(e) {
    if (this._drag) this._drag.offset = e.touches[0].clientX - this._drag.start;
  },
  endDrag() {
    if (!this._drag) return;
    const { index, offset } = this._drag;
    this._drag = null;
    if (Math.abs(offset) < 40) return;
    const to = Math.max(
      0,
      Math.min(this.data.images.length - 1, index + (offset > 0 ? 1 : -1)),
    );
    if (to === index) return;
    const images = this.data.images.slice();
    const image = images.splice(index, 1)[0];
    images.splice(to, 0, image);
    this.setData({ images });
  },
  input(e) {
    this.setData({ [e.currentTarget.dataset.key]: e.detail.value });
  },
  toggle(e) {
    const id = e.currentTarget.dataset.id;
    const dims = this.data.dimensions;
    const chosen = dims.filter((d) => d.selected);
    if (chosen.length >= 3 && !dims.find((d) => d.id === id).selected) {
      api.toast("最多选择3个维度");
      return;
    }
    this.setData({
      dimensions: dims.map((d) => ({
        ...d,
        selected: d.id === id ? !d.selected : d.selected,
      })),
    });
  },
  choose() {
    const remaining = 3 - this.data.images.length;
    if (remaining <= 0) return;
    wx.chooseMedia({
      count: remaining,
      mediaType: ["image"],
      sourceType: ["album", "camera"],
      success: (r) =>
        this.setData({
          images: this.data.images.concat(
            r.tempFiles.map((f) => ({
              path: f.tempFilePath,
              preview: f.tempFilePath,
            })),
          ),
        }),
    });
  },
  removeImage(e) {
    this.setData({
      images: this.data.images.filter(
        (_, i) => i !== e.currentTarget.dataset.index,
      ),
    });
  },
  moveImage(e) {
    const i = e.currentTarget.dataset.index;
    if (i === 0) return;
    const images = this.data.images.slice();
    [images[i - 1], images[i]] = [images[i], images[i - 1]];
    this.setData({ images });
  },
  async save() {
    if (this.data.saving || !api.requireLogin()) return;
    const dimensions = this.data.dimensions
      .filter((d) => d.selected)
      .map((d) => d.id);
    if (!dimensions.length) {
      api.toast("请选择1-3个维度");
      return;
    }
    this.setData({ saving: true });
    try {
      const images = [];
      for (let i = 0; i < this.data.images.length; i++) {
        const image = this.data.images[i];
        const url = image.url || (await api.upload(image.path));
        images.push(url);
        this.setData({ ["images[" + i + "].url"]: url });
      }
      await api.request(
        "/posts" + (this.data.id ? "/" + this.data.id : ""),
        this.data.id ? "PUT" : "POST",
        {
          content: this.data.content,
          dimensions,
          images,
          custom_tags: this.data.customTags.trim()
            ? this.data.customTags.trim().split(/\s+/)
            : [],
          expense_note: this.data.expense,
        },
      );
      api.toast("生活分享已发布");
      wx.navigateBack();
    } catch (e) {
      api.toast(e);
    } finally {
      this.setData({ saving: false });
    }
  },
});
