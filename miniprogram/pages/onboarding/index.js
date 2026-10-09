const api = require("../../utils/api");
Page({
  data: {
    step: 1,
    editing: false,
    years: Array.from({ length: 51 }, (_, i) => 1950 + i),
    ages: Array.from({ length: 26 }, (_, i) => 45 + i),
    months: ["暂不填写", ...Array.from({ length: 12 }, (_, i) => i + 1 + "月")],
    yearIndex: 30,
    ageIndex: 15,
    monthIndex: 0,
    nickname: "",
    city: "",
    bio: "",
    isRetired: false,
    avatar: "",
    avatarPath: "",
    saving: false,
    result: null,
  },
  onLoad() {
    const p = wx.getStorageSync("profile");
    if (p && p.nickname)
      this.setData({
        editing: true,
        step: 2,
        nickname: p.nickname,
        city: p.city || "",
        bio: p.bio || "",
        isRetired: p.is_retired,
        yearIndex: p.birth_year - 1950,
        ageIndex: p.expected_retire_age - 45,
        monthIndex: p.birth_month || 0,
        avatar: api.fullUrl(p.avatar_url),
        avatarPath: p.avatar_url || "",
      });
  },
  begin() {
    this.setData({ step: 2 });
  },
  input(e) {
    this.setData({ [e.currentTarget.dataset.key]: e.detail.value });
  },
  pick(e) {
    this.setData({ [e.currentTarget.dataset.key]: Number(e.detail.value) });
  },
  retired(e) {
    this.setData({ isRetired: e.detail.value });
  },
  city(e) {
    this.setData({ city: e.detail.value.slice(0, 2).join(" ") });
  },
  avatar(e) {
    this.setData({
      avatar: e.detail.avatarUrl,
      avatarPath: e.detail.avatarUrl,
    });
  },
  async save() {
    if (this.data.saving) return;
    const d = this.data;
    const birth = 1950 + d.yearIndex;
    const age = 45 + d.ageIndex;
    if (d.nickname.trim().length < 2) {
      api.toast("昵称需为2-16字");
      return;
    }
    if (!d.isRetired && age <= new Date().getFullYear() - birth) {
      api.toast("退休年龄需大于当前年龄");
      return;
    }
    this.setData({ saving: true });
    try {
      if (!wx.getStorageSync("session")) await api.login();
      let avatar = d.avatarPath;
      if (avatar && !avatar.startsWith("/api/media/"))
        avatar = await api.upload(avatar);
      const result = await api.request("/user/profile", "PUT", {
        nickname: d.nickname,
        birth_year: birth,
        birth_month: d.monthIndex || null,
        expected_retire_age: age,
        is_retired: d.isRetired,
        city: d.city,
        bio: d.bio,
        avatar_url: avatar,
      });
      wx.setStorageSync("profile", result);
      if (d.editing) {
        api.toast("资料已保存");
        wx.navigateBack();
      } else this.setData({ step: 3, result });
    } catch (e) {
      api.toast(e);
    } finally {
      this.setData({ saving: false });
    }
  },
  discover() {
    wx.switchTab({ url: "/pages/discover/index" });
  },
  skip() {
    wx.switchTab({ url: "/pages/discover/index" });
  },
  privacy() {
    wx.navigateTo({ url: "/pages/about/index" });
  },
});
